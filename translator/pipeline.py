import contextlib
import ctypes
import gc
import os
import time
from pathlib import Path

import pgf
from document_loader import load_document, chunk_by_topic

from .config import LANG_CONFIG, OUTPUT_DIR, MODULE_NAME, TOP_N_SIMILAR
from .wordnet import fill_missing_lins, build_generated_entries
from .keywords import extract_keywords
from .expansion import semantic_expansion
from .gf_writer import generate_gf_files, generate_translator_files, compile_grammar
from .wiktionary import WiktionaryLookup
from .apertium import ApertiumLookup

PARSE_PGF_PATH = "./Parse.pgf"


@contextlib.contextmanager
def _suppress_c_stdout():
    """Redirect C-level file descriptor 1 to /dev/null.

    The pgf.Iter C destructor prints 'PGF_SYMBOL_CAPIT' to stdout whenever a
    partially-consumed parse iterator is garbage collected.  This is a bug in
    the pgf C library that cannot be fixed from Python.  We suppress it by
    redirecting fd 1 at the OS level (not just sys.stdout) around the GF parse
    steps that routinely discard partial iterators.
    """
    saved = os.dup(1)
    devnull = os.open('/dev/null', os.O_WRONLY)
    os.dup2(devnull, 1)
    os.close(devnull)
    try:
        yield
    finally:
        gc.collect()  # force C destructors to run while fd 1 is still suppressed
        ctypes.CDLL(None).fflush(None)  # flush C-level output buffers before restoring fd
        os.dup2(saved, 1)
        os.close(saved)

# Cache the loaded Parse.pgf so repeated build_grammar() calls don't re-parse it.
# Parse.pgf is static (never rewritten by the pipeline), so no eviction is needed.
_parse_grammar_cache: dict = {}


def _load_parse_grammar(pgf_path=PARSE_PGF_PATH):
    if pgf_path not in _parse_grammar_cache:
        try:
            _parse_grammar_cache[pgf_path] = pgf.readPGF(pgf_path)
        except Exception as e:
            raise RuntimeError(
                f"Could not load {pgf_path}.\n{e}"
            )
    return _parse_grammar_cache[pgf_path]


def _gf_parse_succeeds(concrete, word: str) -> bool:
    """Return True if word is recognised by the given GF concrete.

    Uses lookupMorpho rather than parse: lookupMorpho is a dictionary lookup
    (sub-millisecond) whereas parse runs a full chart parser (3-4 seconds for
    German due to compound-splitting rules in the RGL).

    Multi-word phrases are rejected immediately — they won't be single WordNet
    lexical entries.
    """
    if " " in word:
        return False
    return bool(concrete.lookupMorpho(word))


def build_grammar(source, source_lang, target_langs,
                  output_dir=OUTPUT_DIR, module_name=MODULE_NAME,
                  n_topics=None, n_words=None, top_n_similar=TOP_N_SIMILAR):
    """
    Full pipeline: extract domain keywords from source, resolve them through
    the lookup chain, write GF files, and compile DomainTranslator.pgf.

    Arguments
    ---------
    source        : file path (str/Path) or raw text string
    source_lang   : language code of the document (e.g. "en", "es")
    target_langs  : list of language codes to compile concretes for
    n_topics      : LDA topic count (None = auto from document size)
    n_words       : keywords per topic (None = auto)
    top_n_similar : fastText neighbours per keyword for semantic expansion

    Returns
    -------
    (pgf_path, surface_map) where surface_map is
    {target_lang: {source_surface: target_surface}} for Wiktionary and
    generated entries, used by the NMT fallback to fix known domain words.

    Lookup chain
    ------------
    Words already in Parse.pgf are available at runtime through ParseLang
    and need no DomainLexicon entry. The pipeline identifies those words,
    then builds DomainLexicon only for what Parse cannot cover.

    1. GF parse (Parse.pgf)  — try parsing each keyword in the source-language
                               concrete. Successes are in WordNet and covered
                               at runtime by Parse{Lang}; no DomainLexicon entry
                               needed. Handles inflected forms automatically.

    2. WiktionaryLookup      — slang, neologisms, and proper nouns not in GF
                               WordNet. DB populated by build_wiktionary_db.py.

    3. ApertiumLookup        — for remaining words, look up source → English,
                               then check if the English word parses in ParseEng.
                               If so, it's in WordNet and covered at runtime.
                               Requires build_apertium_db.py.

    4. build_generated_entries — NMT translation for genuine unknowns (words
                               not found by any of the above). These go into
                               DomainLexicon with translated lins.
    """
    for lang in ([source_lang] + target_langs):
        if lang not in LANG_CONFIG:
            raise ValueError(f"Language '{lang}' not in LANG_CONFIG")

    t = time.perf_counter()
    grammar = _load_parse_grammar()
    src_suffix = LANG_CONFIG[source_lang]["gf_suffix"]
    src_concrete = grammar.languages.get(f"Parse{src_suffix}")
    if not src_concrete:
        raise ValueError(
            f"Parse{src_suffix} not in Parse.pgf — recompile with '{source_lang}' included"
        )
    eng_concrete = grammar.languages.get("ParseEng")
    print(f"Parse.pgf loaded ({time.perf_counter()-t:.1f}s)")

    wikt = WiktionaryLookup()
    apt  = ApertiumLookup()
    from .jmdict import JMdictLookup
    jmd  = JMdictLookup()

    t = time.perf_counter()
    if os.path.exists(str(source)):
        chunks, _ = load_document(source)
    else:
        chunks = chunk_by_topic(str(source))
    print(f"  Document loaded: {len(chunks)} chunks ({time.perf_counter()-t:.1f}s)")

    t = time.perf_counter()
    keywords, all_content = extract_keywords(chunks, source_lang, n_topics, n_words)
    print(f"  Keywords done ({time.perf_counter()-t:.1f}s)")

    t = time.perf_counter()
    if os.path.exists(LANG_CONFIG[source_lang]["fasttext_vec"]):
        expanded = semantic_expansion(keywords, source_lang, top_n_similar)
    else:
        print("  fastText vectors not found, skipping expansion")
        expanded = dict(keywords)
    print(f"  Expansion done ({time.perf_counter()-t:.1f}s)")

    added = {w: cat for w, cat in all_content.items() if w not in expanded}
    expanded.update(added)
    print(f"  +{len(added)} additional content words ({len(expanded)} total)")

    # --- Step 1: GF parse ---
    # Words that parse in Parse{SrcLang} are already in the WordNet grammar.
    # They will be available at runtime through Parse{Lang} concretes and do
    # not need a DomainLexicon entry. GF parsing handles inflected forms, so
    # this catches morphological variants that a surface-form index would miss.
    t = time.perf_counter()
    not_in_wn: dict = {}
    gf_hits = 0
    with _suppress_c_stdout():
        for word, cat in expanded.items():
            if _gf_parse_succeeds(src_concrete, word):
                gf_hits += 1
            else:
                not_in_wn[word] = cat
    print(f"  GF parse: {gf_hits} in WordNet, {len(not_in_wn)} unresolved ({time.perf_counter()-t:.1f}s)")

    # --- Step 2: Wiktionary ---
    wikt_entries, not_in_wn = wikt.build_entries(not_in_wn, source_lang, target_langs)
    if wikt_entries:
        print(f"  Wiktionary: {len(wikt_entries)} entries, {len(not_in_wn)} still unresolved")

    # --- Step 2a: JMdict (Japanese source only) ---
    # JMdict provides ~170k Japanese entries with direct multilingual glosses,
    # covering vocabulary not in GF WordNet or Wiktionary.
    jmd_entries: list = []
    if not_in_wn:
        jmd_entries, not_in_wn = jmd.build_entries(not_in_wn, source_lang, target_langs)
        if jmd_entries:
            print(f"  JMdict: {len(jmd_entries)} entries, {len(not_in_wn)} still unresolved")

    # --- Step 2b: German compound splitting ---
    # Many German domain nouns are compounds (Elektroauto, Ladekabel) whose head
    # component IS in Parse.pgf even though the full compound is not.  For these
    # we use the head's GF function for sense resolution and generation; the
    # surface word in the entry stays as the original compound form.
    if LANG_CONFIG.get(source_lang, {}).get("compound_splitting", False) and not_in_wn:
        from .compound import compound_head as _compound_head
        compound_resolved: dict = {}
        still_unresolved:  dict = {}
        with _suppress_c_stdout():
            for word, cat in not_in_wn.items():
                head = _compound_head(word, src_concrete, cat, LANG_CONFIG[source_lang])
                if head:
                    compound_resolved[word] = (head, cat)
                    gf_hits += 1
                else:
                    still_unresolved[word] = cat
        if compound_resolved:
            print(f"  Compound splitting: {len(compound_resolved)} heads found "
                  f"({len(still_unresolved)} still unresolved)")
        not_in_wn = still_unresolved

    # --- Step 3: Apertium bridge → ParseEng ---
    # For words still unresolved, Apertium may know a source → English mapping.
    # If the English equivalent parses in ParseEng, the word is in WordNet and
    # covered at runtime — no DomainLexicon entry needed.
    # Only applicable for languages where Apertium has a bridge to English.
    if LANG_CONFIG.get(source_lang, {}).get("apertium_to_en", False) and eng_concrete and not_in_wn:
        apt_hits = apt.lookup_batch(list(not_in_wn.keys()), source_lang)
        missing_words: dict = {}
        with _suppress_c_stdout():
            for src_w, cat in not_in_wn.items():
                eng_w = apt_hits.get(src_w.lower())
                if eng_w and _gf_parse_succeeds(eng_concrete, eng_w):
                    pass  # covered by Parse at runtime via English WordNet entry
                else:
                    missing_words[src_w] = cat
        apt_resolved = len(not_in_wn) - len(missing_words)
        print(f"  Apertium: {apt_resolved} resolved via WordNet, {len(missing_words)} unresolved → generated")
    else:
        missing_words = not_in_wn

    # --- Step 4: NMT for genuine unknowns and gap-filling ---
    t = time.perf_counter()
    fill_missing_lins(wikt_entries + jmd_entries, target_langs, source_lang=source_lang)
    print(f"  fill_missing_lins done ({time.perf_counter()-t:.1f}s)")

    t = time.perf_counter()
    generated_entries = build_generated_entries(
        missing_words, target_langs,
        source_lang=source_lang if source_lang != "en" else None,
    )
    print(f"  build_generated_entries done ({time.perf_counter()-t:.1f}s)")

    # Filter out entries whose fun_name already exists in Parse.pgf (WordNet).
    # Redeclaring a WordNet function in DomainLexicon causes a "cannot unify"
    # conflict at GF link time (DomainTranslator = Parse, DomainLexicon).
    existing_fns = set(grammar.functions)
    all_entries = wikt_entries + jmd_entries + generated_entries
    domain_entries = [e for e in all_entries if e["fun_name"] not in existing_fns]
    filtered = len(all_entries) - len(domain_entries)
    if filtered:
        print(f"  Filtered {filtered} entries already in WordNet (would conflict)")

    generate_gf_files(domain_entries, target_langs, output_dir, module_name)
    generate_translator_files(target_langs, output_dir, module_name)
    compile_grammar(target_langs, output_dir)

    pgf_path = str(Path(output_dir) / "DomainTranslator.pgf")
    print(f"\nDone. Grammar compiled → {pgf_path}")

    surface_map = _build_surface_map(wikt_entries + jmd_entries + generated_entries, source_lang, target_langs)
    return pgf_path, surface_map


def _build_surface_map(entries, source_lang, target_langs):
    """
    Build {target_lang: {source_surface: target_surface}} from Wiktionary and
    generated entries for use by the NMT fallback in gf_translator.py.
    """
    from .wordnet import extract_lin_surface
    surface_map = {lang: {} for lang in target_langs if lang != source_lang}
    for entry in entries:
        src_lin = entry["lins"].get(source_lang)
        if not src_lin:
            continue
        src_surface = extract_lin_surface(src_lin)
        if not src_surface:
            continue
        for lang, mapping in surface_map.items():
            tgt_lin = entry["lins"].get(lang)
            if tgt_lin:
                tgt_surface = extract_lin_surface(tgt_lin)
                if tgt_surface:
                    mapping[src_surface.lower()] = tgt_surface
    return surface_map


if __name__ == "__main__":
    from .config import SOURCE_LANG, TARGET_LANGS, SOURCE_TEXT_PATH, MODULE_NAME, NUM_TOPICS, WORDS_PER_TOPIC, TOP_N_SIMILAR

    for lang in [SOURCE_LANG] + TARGET_LANGS:
        if lang not in LANG_CONFIG:
            raise ValueError(f"Language '{lang}' not in LANG_CONFIG")

    pgf_path, _ = build_grammar(
        SOURCE_TEXT_PATH, SOURCE_LANG, TARGET_LANGS,
        module_name=MODULE_NAME,
        n_topics=NUM_TOPICS,
        n_words=WORDS_PER_TOPIC,
        top_n_similar=TOP_N_SIMILAR,
    )
    print(f"\nFiles written to {pgf_path}")
