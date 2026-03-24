import os
import time
from pathlib import Path

from document_loader import load_document, chunk_by_topic

from .config import LANG_CONFIG, DB_PATH, OUTPUT_DIR, MODULE_NAME, TOP_N_SIMILAR
from .wordnet import build_wordnet_index, wordnet_lookup, fill_missing_lins, build_generated_entries, extract_lin_surface
from .keywords import extract_keywords
from .expansion import semantic_expansion
from .nmt import translate_batch
from .gf_writer import generate_gf_files, generate_translator_files, compile_grammar


def build_grammar(source, source_lang, target_langs,
                  output_dir=OUTPUT_DIR, module_name=MODULE_NAME,
                  n_topics=None, n_words=None, top_n_similar=TOP_N_SIMILAR):
    """
    Full pipeline: extract domain keywords from source, look them up in
    WordNet, fill missing translations via NMT, write GF files, and compile
    DomainTranslator.pgf.

    source        : file path (str/Path) or raw text string
    source_lang   : language code of the document (e.g. "en", "ja")
    target_langs  : list of language codes to compile concretes for
    n_topics      : LDA topic count (None = auto)
    n_words       : keywords per topic (None = auto)
    top_n_similar : fastText neighbours per keyword

    Returns (pgf_path, surface_map) where surface_map is
    {target_lang: {source_surface: target_surface}} for NMT post-processing.
    """
    for lang in ([source_lang] + target_langs):
        if lang not in LANG_CONFIG:
            raise ValueError(f"Language '{lang}' not in LANG_CONFIG")

    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(f"WordNet DB not found at {DB_PATH}")

    t = time.perf_counter()
    print("Loading WordNet index...")
    wn_index, surface_index = build_wordnet_index(DB_PATH)
    print(f"  {sum(len(v) for v in wn_index.values()):,} entries indexed ({time.perf_counter()-t:.1f}s)\n")

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

    if source_lang != "en":
        src_surface_map = surface_index.get(source_lang, {})
        db_resolved, nmt_needed = {}, {}
        for src_w, cat in expanded.items():
            eng_w = src_surface_map.get(src_w.lower())
            if eng_w:
                db_resolved[eng_w] = cat
            else:
                nmt_needed[src_w] = cat
        print(f"  DB resolved: {len(db_resolved)}, NMT needed: {len(nmt_needed)}")

        english_expanded = dict(db_resolved)
        if nmt_needed:
            t = time.perf_counter()
            print(f"Translating {len(nmt_needed)} source words to English via NMT...")
            word_list = list(nmt_needed.keys())
            try:
                english_words_list = translate_batch(word_list, source_lang, "en")
                for src_w, eng_w in zip(word_list, english_words_list):
                    if eng_w:
                        english_expanded[eng_w] = nmt_needed[src_w]
            except Exception as e:
                print(f"  Translation to English failed: {e}. Using source words as-is.")
                english_expanded.update(nmt_needed)
            print(f"  NMT source→en done ({time.perf_counter()-t:.1f}s)")
    else:
        english_expanded = expanded

    found_entries, missing_words = wordnet_lookup(english_expanded, wn_index)

    t = time.perf_counter()
    fill_missing_lins(found_entries, target_langs)
    print(f"  fill_missing_lins done ({time.perf_counter()-t:.1f}s)")

    t = time.perf_counter()
    generated_entries = build_generated_entries(missing_words, target_langs)
    print(f"  build_generated_entries done ({time.perf_counter()-t:.1f}s)")

    generate_gf_files(found_entries, generated_entries, target_langs, output_dir, module_name)
    generate_translator_files(target_langs, output_dir, module_name)
    compile_grammar(target_langs, output_dir)

    pgf_path = str(Path(output_dir) / "DomainTranslator.pgf")
    print(f"\nDone. Grammar compiled → {pgf_path}")

    surface_map = _build_surface_map(generated_entries, source_lang, target_langs)
    return pgf_path, surface_map


def _build_surface_map(generated_entries, source_lang, target_langs):
    """
    Build {target_lang: {source_surface: target_surface}} from generated entries
    for NMT fallback post-processing.
    """
    surface_map = {lang: {} for lang in target_langs if lang != source_lang}
    for entry in generated_entries:
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
