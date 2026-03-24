import os
import re
import shutil
import sqlite3
import subprocess
from pathlib import Path
from document_loader import load_document
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.decomposition import LatentDirichletAllocation
from gensim.models import KeyedVectors
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM, MarianTokenizer, MarianMTModel
import spacy

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DB_PATH = "./gf_wordnet.db"
OUTPUT_DIR = "./resources/DomainLexicon"

GF_WORDNET_DIR = "/usr/share/gf-3.11/gf-wordnet"
GF_WORDNET_BUILD_GFO = "/usr/share/gf-3.11/gf-wordnet/build/gfo"

# Per-language NLP and GF config.
# gf_cat_module : the Cat concrete to extend (CatEng, CatSpa, CatGer, CatZero, ...)
# gf_open       : open clause for the concrete header — mirrors the corresponding WordNet*.gf
# gf_db_column  : DB column holding lin expressions for this language (None if not yet in DB)
# gf_zero_morph : True for languages using CatZero/ParadigmsZero (no full RGL morphology)
LANG_CONFIG = {
    "en": {
        "spacy_model": "en_core_web_sm",
        "fasttext_vec": "./resources/cc.en.300.vec",
        "gf_suffix": "Eng",
        "gf_cat_module": "CatEng",
        "gf_open": (
            "MorphoEng, ResEng, ParadigmsEng, IrregEng, ExtraEng, "
            "(G = GrammarEng), (C = ConstructX), Prelude"
        ),
        "gf_db_column": "eng_lin",
        "gf_zero_morph": False,
    },
    "es": {
        "spacy_model": "es_core_news_sm",
        "fasttext_vec": "./resources/cc.es.300.vec",
        "gf_suffix": "Spa",
        "gf_cat_module": "CatSpa",
        "gf_open": (
            "ConstructionSpa, GrammarSpa, ParadigmsSpa, ParamX, "
            "(S = StructuralSpa), (E = ExtendSpa), (L = LexiconSpa), "
            "(I = IrregSpa), (M = MorphoSpa), (R = ResSpa), Prelude"
        ),
        "gf_db_column": "spa_lin",
        "gf_zero_morph": False,
    },
    "de": {
        "spacy_model": "de_core_news_sm",
        "fasttext_vec": "./resources/cc.de.300.vec",
        "gf_suffix": "Ger",
        "gf_cat_module": "CatGer",
        "gf_open": (
            "Prelude, ParadigmsGer, GrammarGer, "
            "(M = MorphoGer), (S = StructuralGer), (ResGer = ResGer)"
        ),
        "gf_db_column": None,
        "gf_zero_morph": False,
    },
    "ja": {
        "spacy_model": "ja_core_news_sm",
        "fasttext_vec": "./resources/cc.ja.300.vec",
        "gf_suffix": "Jpn",
        "gf_cat_module": "CatZero",
        "gf_open": "ParadigmsZero",
        "gf_db_column": None,
        "gf_zero_morph": True,
    },
    # Add more languages here following the same pattern.
    # For languages with full RGL support: set gf_cat_module = "Cat{Suffix}",
    #   gf_open to match the corresponding WordNet*.gf header, gf_zero_morph = False.
    # For languages without full RGL (or where only surface forms are needed):
    #   set gf_cat_module = "CatZero", gf_open = "ParadigmsZero", gf_zero_morph = True.
}

MARIAN_MODELS = {
    "en-es": "Helsinki-NLP/opus-mt-en-es",
    "es-en": "Helsinki-NLP/opus-mt-es-en",
    "de-es": "Helsinki-NLP/opus-mt-de-es",
    "es-de": "Helsinki-NLP/opus-mt-es-de",
    "en-de": "Helsinki-NLP/opus-mt-en-de",
    "de-en": "Helsinki-NLP/opus-mt-de-en",
    "en-ja": "Helsinki-NLP/opus-mt-en-ja",
    "ja-en": "Helsinki-NLP/opus-mt-ja-en",
}
M2M100_MODEL = "facebook/m2m100_418M"

# spaCy POS tag → GF category
SPACY_TO_GF = {
    "NOUN": "N",
    "PROPN": "PN",
    "VERB": "V2",
    "ADJ": "A",
    "ADV": "Adv",
}
DEFAULT_GF_CAT = "N"

# ---------------------------------------------------------------------------
# User-defined run parameters
# ---------------------------------------------------------------------------

SOURCE_LANG = "ja"
TARGET_LANGS = ["en", "es", "de", "ja"]   # all languages to generate GF concretes for
SOURCE_TEXT_PATH = "./resources/sample_document_ja.txt"
MODULE_NAME = "DomainLexicon"
NUM_TOPICS = 5
WORDS_PER_TOPIC = 5
TOP_N_SIMILAR = 20

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_base_word(fun_name):
    """
    Derive a normalised lookup key from a DB fun_name.
      battery_1_N     → battery
      electric_fire_N → electric_fire
      electricianMasc_N → electrician
      abandon_1_V2    → abandon
    """
    s = fun_name
    s = re.sub(r"(Masc|Fem|Pl|Sg)$", "", s)     # strip gender/number suffix
    s = re.sub(r"_[A-Z][A-Za-z0-9]*$", "", s)    # strip GF category
    s = re.sub(r"_\d+$", "", s)                   # strip sense number
    return s.lower()


def _make_fun_name(english_word, gf_cat):
    """Create a valid GF identifier from an English word and category."""
    normalized = re.sub(r"[^a-z0-9]", "_", english_word.lower())
    normalized = re.sub(r"_+", "_", normalized).strip("_") or "unknown"
    # GF identifiers must not start with a digit
    if normalized[0].isdigit():
        normalized = f"n_{normalized}"
    return f"{normalized}_{gf_cat}"


def _make_lin_expr(surface_form, gf_cat, lang_code):
    """
    Generate a minimal RGL paradigm call for a surface form.
    Uses ParadigmsZero for zero-morphology languages, full RGL paradigms otherwise.
    """
    w = surface_form.replace('"', '\\"')
    if LANG_CONFIG[lang_code]["gf_zero_morph"]:
        # ParadigmsZero: all mk* take a single string
        fn = {"V2": "mkV2", "V": "mkV", "A": "mkA", "Adv": "mkAdv", "PN": "mkPN"}.get(gf_cat, "mkN")
        return f'{fn} "{w}"'
    else:
        # Full RGL: V2 wraps mkV
        if gf_cat == "V2":
            return f'mkV2 (mkV "{w}")'
        fn = {"V": "mkV", "A": "mkA", "Adv": "mkAdv", "PN": "mkPN"}.get(gf_cat, "mkN")
        return f'{fn} "{w}"'

# ---------------------------------------------------------------------------
# Step 0 — WordNet index
# ---------------------------------------------------------------------------

def build_wordnet_index(db_path):
    """
    Build an in-memory index from English base word → list of DB entries.
    Each entry: {fun_name, category, src_word, lins: {lang_code: lin_expr}}

    Only languages with a configured gf_db_column are included in lins.
    Entries where lin is NULL, empty, or 'variants {}' are omitted from lins
    (the key is simply absent, so they get filled via NMT later).
    """
    db_langs = {
        code: cfg["gf_db_column"]
        for code, cfg in LANG_CONFIG.items()
        if cfg.get("gf_db_column")
    }  # e.g. {"en": "eng_lin", "es": "spa_lin"}

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cols = list(db_langs.values())
    cur.execute(f"SELECT fun_name, category, {', '.join(cols)} FROM functions")

    index = {}
    for row in cur.fetchall():
        fun_name, category = row[0], row[1]
        lins = {}
        for i, (lang_code, _) in enumerate(db_langs.items()):
            val = row[2 + i]
            if val and val.strip() and val != "variants {}":
                lins[lang_code] = val

        base = _extract_base_word(fun_name)
        entry = {
            "fun_name": fun_name,
            "category": category,
            "src_word": base,
            "lins": lins,
        }
        index.setdefault(base, []).append(entry)

    conn.close()
    return index

# ---------------------------------------------------------------------------
# Step 1 — Keyword extraction
# ---------------------------------------------------------------------------

def load_text(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _auto_topics(n_chunks: int, vocab_size: int) -> tuple[int, int]:
    """Derive sensible n_topics and n_words from document statistics."""
    # One topic per ~15 chunks, between 2 and 12
    n_topics = max(2, min(12, n_chunks // 15))
    # Enough words to cover vocabulary without excessive overlap across topics
    n_words = max(5, min(20, vocab_size // (n_topics * 4)))
    return n_topics, n_words


def extract_keywords(chunks, lang_code, n_topics=None, n_words=None):
    """
    LDA topic modelling on a list of text chunks (e.g. subtitle blocks,
    paragraphs).  Each chunk is treated as a separate document so LDA can
    find distinct topics.

    chunks    : list[str] from document_loader.load_document()
    n_topics  : number of LDA topics (None = auto-derive from document size)
    n_words   : keywords per topic   (None = auto-derive from vocabulary size)
    Returns dict {lemma: gf_category} for the top keywords.
    """
    print(f"1. Topic modelling on {lang_code.upper()} ({len(chunks)} chunks)...")

    nlp = spacy.load(LANG_CONFIG[lang_code]["spacy_model"])

    token_pos = {}
    processed_chunks = []
    for chunk in chunks:
        doc = nlp(chunk)
        lemmas = []
        for t in doc:
            if t.is_punct or t.is_space or t.is_digit or t.is_stop:
                continue
            if lang_code == "ja" and t.pos_ == "SYM":
                continue
            lemma = t.lemma_.lower()
            token_pos[lemma] = SPACY_TO_GF.get(t.pos_, DEFAULT_GF_CAT)
            lemmas.append(lemma)
        if lemmas:
            processed_chunks.append(" ".join(lemmas))

    if not processed_chunks:
        print("  Warning: no meaningful tokens found.")
        return {}

    vectorizer = TfidfVectorizer(max_df=0.95, min_df=1, stop_words=None)
    dtm = vectorizer.fit_transform(processed_chunks)
    vocab_size = len(vectorizer.vocabulary_)

    auto_t, auto_w = _auto_topics(len(processed_chunks), vocab_size)
    resolved_topics: int = n_topics if n_topics is not None else auto_t
    resolved_words:  int = n_words  if n_words  is not None else auto_w
    if n_topics is None or n_words is None:
        print(f"  Auto: {resolved_topics} topics × {resolved_words} words (vocab={vocab_size})")

    effective_topics = min(resolved_topics, dtm.shape[0])
    lda = LatentDirichletAllocation(n_components=effective_topics, random_state=42)
    lda.fit(dtm)

    feature_names = vectorizer.get_feature_names_out()
    keywords = {}
    for topic_idx, topic in enumerate(lda.components_):
        top_idx = topic.argsort()[:-resolved_words - 1:-1]
        top_words = [str(feature_names[i]) for i in top_idx]
        for w in top_words:
            keywords[w] = token_pos.get(w, DEFAULT_GF_CAT)
        print(f"  Topic {topic_idx}: {', '.join(top_words)}")

    return keywords

# ---------------------------------------------------------------------------
# Step 2 — Semantic expansion
# ---------------------------------------------------------------------------

def semantic_expansion(keywords, lang_code, top_n):
    """
    Expand keywords using fastText vectors.
    Returns dict {word: gf_category}; expanded words default to N.
    """
    vectors_path = LANG_CONFIG[lang_code]["fasttext_vec"]
    print(f"2. Expanding with fastText vectors for {lang_code.upper()}...")

    try:
        ft = KeyedVectors.load_word2vec_format(vectors_path, binary=False, limit=200000)
    except Exception as e:
        print(f"  Could not load fastText model: {e}")
        return dict(keywords)

    expanded = dict(keywords)
    for word in list(keywords):
        try:
            for similar, _ in ft.most_similar(word, topn=top_n):
                if len(similar) > 2 and similar.isalpha() and similar not in expanded:
                    expanded[similar] = DEFAULT_GF_CAT
        except KeyError:
            pass

    print(f"  {len(keywords)} keywords → {len(expanded)} after expansion")
    return expanded

# ---------------------------------------------------------------------------
# Step 3 — NMT translation (low-level batch)
# ---------------------------------------------------------------------------

_nmt_model_cache: dict = {}

def _load_nmt_model(source_lang, target_lang):
    """Load and cache NMT tokenizer+model for a language pair."""
    key = f"{source_lang}-{target_lang}"
    if key not in _nmt_model_cache:
        model_name = MARIAN_MODELS.get(key)
        if model_name:
            print(f"  Loading NMT model {model_name} (downloading if not cached)...")
            tokenizer = MarianTokenizer.from_pretrained(model_name)
            model = MarianMTModel.from_pretrained(model_name)
        else:
            print(f"  No direct model for {key}, using M2M-100")
            model_name = M2M100_MODEL
            print(f"  Loading NMT model {model_name} (downloading if not cached)...")
            tokenizer = AutoTokenizer.from_pretrained(model_name)
            model = AutoModelForSeq2SeqLM.from_pretrained(model_name)
            tokenizer.src_lang = source_lang
        print(f"  Model loaded.")
        _nmt_model_cache[key] = (tokenizer, model, model_name)
    return _nmt_model_cache[key]


def translate_batch(words, source_lang, target_lang):
    """
    Translate a list of words/phrases from source_lang to target_lang.
    Returns list of translated strings in the same order.
    Raises on failure so callers can handle explicitly.
    """
    if source_lang == target_lang:
        return list(words)

    tokenizer, model, model_name = _load_nmt_model(source_lang, target_lang)

    translated = []
    batch_size = 64
    for i in range(0, len(words), batch_size):
        batch = list(words[i : i + batch_size])
        inputs = tokenizer(batch, return_tensors="pt", padding=True, truncation=True)
        if model_name == M2M100_MODEL:
            out = model.generate(**inputs, forced_bos_token_id=tokenizer.get_lang_id(target_lang))
        else:
            out = model.generate(**inputs)
        translated.extend(tokenizer.decode(t, skip_special_tokens=True) for t in out)

    return translated

# ---------------------------------------------------------------------------
# Step 4 — WordNet lookup + gap-fill
# ---------------------------------------------------------------------------

def wordnet_lookup(english_words, wn_index):
    """
    Look up English words in the WordNet index.

    english_words : dict {word: gf_cat}
    wn_index      : from build_wordnet_index()

    Returns:
        found_entries : list of entry dicts (all DB senses for found words)
        missing_words : dict {word: gf_cat} for words not in the DB
    """
    print("3. Looking up words in GF WordNet database...")
    found_entries = []
    missing_words = {}
    seen_fun_names = set()

    for word, cat in english_words.items():
        key = re.sub(r"[^a-z0-9]", "_", word.lower())
        key = re.sub(r"_+", "_", key).strip("_")

        if key in wn_index:
            entries = wn_index[key]
            for e in entries:
                if e["fun_name"] not in seen_fun_names:
                    found_entries.append(e)
                    seen_fun_names.add(e["fun_name"])
        else:
            missing_words[word] = cat

    n_found = len(english_words) - len(missing_words)
    print(f"  WordNet: {n_found}/{len(english_words)} words found "
          f"({len(found_entries)} total entries incl. senses)")
    return found_entries, missing_words


def fill_missing_lins(entries, target_langs):
    """
    For found DB entries that lack lin expressions for some target languages,
    translate from English to fill the gaps.
    Modifies entries in place.
    """
    langs_needing_fill = [
        lang for lang in target_langs
        if LANG_CONFIG.get(lang) and not LANG_CONFIG[lang].get("gf_db_column")
    ]
    if not langs_needing_fill:
        return

    print(f"  Filling missing lins via NMT for: {', '.join(langs_needing_fill)}")

    # Group entries by their English surface form to batch translate
    # Extract the surface form from the eng_lin expression (e.g. mkN "battery" → battery)
    def extract_surface(lin_expr):
        m = re.search(r'"([^"]+)"', lin_expr)
        return m.group(1) if m else None

    for lang in langs_needing_fill:
        to_translate = []   # (entry_index, surface_form, gf_cat)
        for i, entry in enumerate(entries):
            if lang not in entry["lins"] and "en" in entry["lins"]:
                surface = extract_surface(entry["lins"]["en"])
                if surface:
                    to_translate.append((i, surface, entry["category"]))

        if not to_translate:
            continue

        words = [t[1] for t in to_translate]
        try:
            translated = translate_batch(words, "en", lang)
            for (idx, _, cat), trans_word in zip(to_translate, translated):
                entries[idx]["lins"][lang] = _make_lin_expr(trans_word, cat, lang)
        except Exception as e:
            print(f"  Warning: fill translation to {lang} failed: {e}")

# ---------------------------------------------------------------------------
# Step 5 — Generate entries for words not in WordNet
# ---------------------------------------------------------------------------

def build_generated_entries(missing_words, target_langs):
    """
    For words not found in the WordNet DB, translate to each target language
    and construct GF entry dicts using simple paradigm calls.

    missing_words : dict {english_word: gf_cat}
    source_lang   : the language the words are currently in
                    (already translated to English before this call if source != en)
    """
    if not missing_words:
        return []

    print(f"4. Generating entries for {len(missing_words)} words not in WordNet...")
    word_list = list(missing_words.keys())
    cat_list = [missing_words[w] for w in word_list]

    # Translate English words to each target language
    lang_translations = {}
    for lang in target_langs:
        if lang == "en":
            lang_translations["en"] = word_list
            continue
        print(f"   Translating to {lang.upper()}...")
        try:
            lang_translations[lang] = translate_batch(word_list, "en", lang)
        except Exception as e:
            print(f"   Warning: translation to {lang} failed: {e}")
            lang_translations[lang] = [""] * len(word_list)

    entries = []
    for i, (word, cat) in enumerate(zip(word_list, cat_list)):
        fun_name = _make_fun_name(word, cat)
        lins = {}
        for lang in target_langs:
            surface = lang_translations.get(lang, [])[i] if i < len(lang_translations.get(lang, [])) else ""
            if surface:
                lins[lang] = _make_lin_expr(surface, cat, lang)
        entries.append({"fun_name": fun_name, "category": cat, "src_word": word, "lins": lins})

    return entries

# ---------------------------------------------------------------------------
# Step 6 — Write GF files
# ---------------------------------------------------------------------------

def generate_gf_files(found_entries, generated_entries, target_langs, output_dir, module_name):
    """
    Write abstract DomainLexicon.gf and one concrete per target language.

    Abstract:  abstract {module_name} = Cat ** { fun ... }
    Concrete:  concrete {module_name}{Suffix} of {module_name} = Cat{Suffix} ** open ... in { lin ... }

    Only generated_entries (words NOT in WordNet) go into the abstract/concretes.
    found_entries are already declared in the WordNet abstract and available via
    Parse{Lang} — redeclaring them would cause a "cannot unify" conflict at link time.
    Entries with no lin for a language get variants {} as a placeholder.
    """
    print(f"5. Writing GF files to {output_dir}/...")
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    if found_entries:
        print(f"  WordNet entries ({len(found_entries)}) already available via Parse{{Lang}} — not redeclared.")

    # Only new (non-WordNet) entries go into DomainLexicon
    seen = {}
    for e in generated_entries:
        seen.setdefault(e["fun_name"], e)
    unique = sorted(seen.values(), key=lambda e: e["fun_name"])

    if not unique:
        print("  No entries to write.")
        return

    # Abstract
    abstract_lines = [
        f"abstract {module_name} = Cat ** {{",
        "  fun",
    ]
    for e in unique:
        abstract_lines.append(f"    {e['fun_name']} : {e['category']} ;")
    abstract_lines.append("}")
    abstract_path = Path(output_dir) / f"{module_name}.gf"
    abstract_path.write_text("\n".join(abstract_lines) + "\n", encoding="utf-8")
    print(f"  {abstract_path.name}: {len(unique)} functions")

    # Concretes
    for lang in target_langs:
        cfg = LANG_CONFIG.get(lang)
        if not cfg:
            print(f"  WARNING: no config for '{lang}', skipping")
            continue

        suffix = cfg["gf_suffix"]
        concrete_name = f"{module_name}{suffix}"
        lines = [
            f"concrete {concrete_name} of {module_name} = {cfg['gf_cat_module']} ** open {cfg['gf_open']} in {{",
            "  lin",
        ]
        covered = 0
        for e in unique:
            lin = e["lins"].get(lang)
            if lin:
                lines.append(f"    {e['fun_name']} = {lin} ;")
                covered += 1
            else:
                lines.append(f"    {e['fun_name']} = variants {{}} ;")
        lines.append("}")

        out_path = Path(output_dir) / f"{concrete_name}.gf"
        out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"  {out_path.name}: {covered}/{len(unique)} entries translated")

# ---------------------------------------------------------------------------
# Step 7 — Write DomainTranslator grammar files
# ---------------------------------------------------------------------------

# Languages that have pre-compiled Parse*.gfo in the gf-wordnet root or build/gfo.
# GF uses these to avoid recompiling the full WordNet source (which is very slow).
# Keys must match gf_suffix values in LANG_CONFIG.
_PRECOMPILED_GFO = {
    # Already in gf-wordnet root — no staging needed
    "Eng": [],
    "Spa": [],
    # Need to be copied from build/gfo into gf-wordnet root before compile
    "Ger": ["ParseGer.gfo", "WordNetGer.gfo", "ParseExtendGer.gfo"],
    # Jpn uses CatZero — no WordNet gfo needed, compiles from source quickly
    "Jpn": [],
}


def stage_gfo_files(suffix):
    """Copy pre-compiled gfo files for a language into the gf-wordnet root so GF
    finds them without recompiling the full WordNet source."""
    files = _PRECOMPILED_GFO.get(suffix, [])
    for fname in files:
        src = Path(GF_WORDNET_BUILD_GFO) / fname
        dst = Path(GF_WORDNET_DIR) / fname
        if src.exists() and not dst.exists():
            shutil.copy2(src, dst)
            print(f"  Staged {fname} → gf-wordnet root")


def generate_translator_files(target_langs, output_dir, module_name):
    """
    Write DomainTranslator.gf (abstract) and one concrete per target language.

    Abstract:  abstract DomainTranslator = Parse, DomainLexicon ** {}
    Concrete:  concrete DomainTranslatorEng of DomainTranslator = ParseEng, DomainLexiconEng ** {}
    """
    print(f"6. Writing DomainTranslator GF files...")
    translator_name = f"Domain{module_name[0].upper()}{module_name[1:]}Translator" \
        if not module_name.startswith("Domain") else f"{module_name}Translator"
    # Simpler: always name it DomainTranslator
    translator_name = "DomainTranslator"

    # Abstract
    abstract_path = Path(output_dir) / f"{translator_name}.gf"
    abstract_path.write_text(
        f"abstract {translator_name} = Parse, {module_name} ** {{}}\n",
        encoding="utf-8",
    )
    print(f"  {abstract_path.name}")

    # Concretes
    for lang in target_langs:
        cfg = LANG_CONFIG.get(lang)
        if not cfg:
            continue
        suffix = cfg["gf_suffix"]
        concrete_name = f"{translator_name}{suffix}"
        concrete_path = Path(output_dir) / f"{concrete_name}.gf"
        concrete_path.write_text(
            f"concrete {concrete_name} of {translator_name} = "
            f"Parse{suffix}, {module_name}{suffix} ** {{}}\n",
            encoding="utf-8",
        )
        print(f"  {concrete_path.name}")


# ---------------------------------------------------------------------------
# Step 8 — Compile to PGF
# ---------------------------------------------------------------------------

def compile_grammar(target_langs, output_dir):
    """
    Compile DomainTranslator*.gf into DomainTranslator.pgf for the configured
    target languages.  First-time compile for a language may be slow if its
    Parse*.gfo hasn't been cached yet; subsequent runs use cached .gfo files.
    """
    print(f"7. Compiling DomainTranslator.pgf...")
    translator_name = "DomainTranslator"
    out = Path(output_dir)

    # Stage any pre-built gfo files (e.g. Ger) into gf-wordnet root so GF
    # finds them without recompiling the full WordNet source.
    for lang in target_langs:
        cfg = LANG_CONFIG.get(lang)
        if cfg:
            stage_gfo_files(cfg["gf_suffix"])

    concrete_files = []
    for lang in target_langs:
        cfg = LANG_CONFIG.get(lang)
        if not cfg:
            continue
        f = out / f"{translator_name}{cfg['gf_suffix']}.gf"
        if f.exists():
            concrete_files.append(str(f))

    if not concrete_files:
        print("  No concrete files found, skipping compile.")
        return

    cmd = [
        "gf", "--make",
        f"-name={translator_name}",
        f"--output-dir={output_dir}",
        f"-path={output_dir}:{GF_WORDNET_DIR}",
    ] + concrete_files

    print(f"  gf --make [{', '.join(target_langs)}]")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"  Compile FAILED (exit {result.returncode})")
            # Show all stderr — GF errors can appear anywhere in the output
            for line in result.stderr.splitlines():
                print(f"    {line}")
            print(f"  Full command: {' '.join(cmd)}")
        else:
            print(f"  OK → {out / (translator_name + '.pgf')}")
    except FileNotFoundError:
        print("  'gf' binary not found — is GF installed and on PATH?")


# ---------------------------------------------------------------------------
# build_grammar — callable entry point used by morphologizinator
# ---------------------------------------------------------------------------

def build_grammar(source, source_lang, target_langs,
                  output_dir=OUTPUT_DIR, module_name=MODULE_NAME):
    """
    Full pipeline: extract domain keywords from source, look them up in
    WordNet, fill missing translations via NMT, write GF files, and compile
    DomainTranslator.pgf.

    source       : file path (str/Path) or raw text string
    source_lang  : language code of the document (e.g. "en", "ja")
    target_langs : list of language codes to compile concretes for (e.g. ["en","es"])
    """
    for lang in ([source_lang] + target_langs):
        if lang not in LANG_CONFIG:
            raise ValueError(f"Language '{lang}' not in LANG_CONFIG")

    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(f"WordNet DB not found at {DB_PATH}")
    print("Loading WordNet index...")
    wn_index = build_wordnet_index(DB_PATH)
    print(f"  {sum(len(v) for v in wn_index.values()):,} entries indexed\n")

    if os.path.exists(str(source)):
        chunks, _ = load_document(source)
    else:
        # Raw text passed directly — split into lines as chunks
        chunks = [l for l in str(source).splitlines() if l.strip()]

    keywords = extract_keywords(chunks, source_lang)

    if os.path.exists(LANG_CONFIG[source_lang]["fasttext_vec"]):
        expanded = semantic_expansion(keywords, source_lang, TOP_N_SIMILAR)
    else:
        print("  fastText vectors not found, skipping expansion")
        expanded = keywords

    if source_lang != "en":
        print(f"Translating {len(expanded)} source words to English for DB lookup...")
        word_list = list(expanded.keys())
        try:
            english_words_list = translate_batch(word_list, source_lang, "en")
            english_expanded = {}
            for src_w, eng_w in zip(word_list, english_words_list):
                if eng_w:
                    english_expanded[eng_w] = expanded[src_w]
        except Exception as e:
            print(f"  Translation to English failed: {e}. Using source words as-is.")
            english_expanded = expanded
    else:
        english_expanded = expanded

    found_entries, missing_words = wordnet_lookup(english_expanded, wn_index)
    fill_missing_lins(found_entries, target_langs)
    generated_entries = build_generated_entries(missing_words, target_langs)

    generate_gf_files(found_entries, generated_entries, target_langs, output_dir, module_name)
    generate_translator_files(target_langs, output_dir, module_name)
    compile_grammar(target_langs, output_dir)

    pgf_path = str(Path(output_dir) / "DomainTranslator.pgf")
    print(f"\nDone. Grammar compiled → {pgf_path}")
    return pgf_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Validate config
    for lang in [SOURCE_LANG] + TARGET_LANGS:
        if lang not in LANG_CONFIG:
            raise ValueError(f"Language '{lang}' not in LANG_CONFIG")

    # Load WordNet index once
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(f"WordNet DB not found at {DB_PATH}")
    print("Loading WordNet index...")
    wn_index = build_wordnet_index(DB_PATH)
    print(f"  {sum(len(v) for v in wn_index.values()):,} entries indexed\n")

    # 1. Load document and extract keywords
    chunks, _ = load_document(SOURCE_TEXT_PATH)
    keywords = extract_keywords(chunks, SOURCE_LANG, NUM_TOPICS, WORDS_PER_TOPIC)

    # 2. Semantic expansion in source language
    if os.path.exists(LANG_CONFIG[SOURCE_LANG]["fasttext_vec"]):
        expanded = semantic_expansion(keywords, SOURCE_LANG, TOP_N_SIMILAR)
    else:
        print("  fastText vectors not found, skipping expansion")
        expanded = keywords

    # 3. Translate to English for DB lookup (no-op if source is already English)
    if SOURCE_LANG != "en":
        print(f"3. Translating {len(expanded)} source words to English for DB lookup...")
        word_list = list(expanded.keys())
        try:
            english_words_list = translate_batch(word_list, SOURCE_LANG, "en")
            # Rebuild dict with English words, preserving GF category from source
            english_expanded = {}
            for src_w, eng_w in zip(word_list, english_words_list):
                if eng_w:
                    english_expanded[eng_w] = expanded[src_w]
        except Exception as e:
            print(f"  Translation to English failed: {e}. Using source words as-is.")
            english_expanded = expanded
    else:
        english_expanded = expanded

    # 4. WordNet lookup
    found_entries, missing_words = wordnet_lookup(english_expanded, wn_index)

    # Fill in target language lins for found entries that lack them
    fill_missing_lins(found_entries, TARGET_LANGS)

    # 5. Build entries for words not in WordNet
    generated_entries = build_generated_entries(missing_words, TARGET_LANGS)

    # 6. Write GF files
    generate_gf_files(found_entries, generated_entries, TARGET_LANGS, OUTPUT_DIR, MODULE_NAME)

    # 7. Write DomainTranslator grammar files
    generate_translator_files(TARGET_LANGS, OUTPUT_DIR, MODULE_NAME)

    # 8. Compile to PGF
    compile_grammar(TARGET_LANGS, OUTPUT_DIR)


    print(f"\nDone. Files written to {OUTPUT_DIR}/")
    print(f"  Found in WordNet: {len(found_entries)} entries")
    print(f"  Generated (new):  {len(generated_entries)} entries")
