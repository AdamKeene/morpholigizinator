import re
import sqlite3

from .config import LANG_CONFIG, DEFAULT_GF_CAT
from .nmt import translate_batch


def _extract_base_word(fun_name):
    """Derive a normalised English lookup key from a DB fun_name."""
    s = fun_name
    s = re.sub(r"(Masc|Fem|Pl|Sg)$", "", s)
    s = re.sub(r"_[A-Z][A-Za-z0-9]*$", "", s)
    s = re.sub(r"_\d+$", "", s)
    return s.lower()


def _make_fun_name(english_word, gf_cat):
    """Create a valid GF identifier from an English word and category."""
    normalized = re.sub(r"[^a-z0-9]", "_", english_word.lower())
    normalized = re.sub(r"_+", "_", normalized).strip("_") or "unknown"
    if normalized[0].isdigit():
        normalized = f"n_{normalized}"
    return f"{normalized}_{gf_cat}"


def _make_lin_expr(surface_form, gf_cat, lang_code):
    """Generate a minimal RGL paradigm call for a surface form."""
    w = surface_form.replace('"', '\\"')
    if LANG_CONFIG[lang_code]["gf_zero_morph"]:
        fn = {"V2": "mkV2", "V": "mkV", "A": "mkA", "Adv": "mkAdv", "PN": "mkPN"}.get(gf_cat, "mkN")
        return f'{fn} "{w}"'
    else:
        if gf_cat == "V2":
            return f'mkV2 (mkV "{w}")'
        fn = {"V": "mkV", "A": "mkA", "Adv": "mkAdv", "PN": "mkPN"}.get(gf_cat, "mkN")
        return f'{fn} "{w}"'


def extract_lin_surface(lin_expr):
    """Extract the first quoted surface form from a GF lin expression."""
    m = re.search(r'"([^"]+)"', lin_expr)
    return m.group(1) if m else None


def build_wordnet_index(db_path):
    """
    Build two indices from the WordNet DB:

    index         : {english_base_word: [entry, ...]}
    surface_index : {lang_code: {surface_form: english_surface}} for all
                    non-English DB languages, enabling direct source-language
                    lookup without NMT translation.
    """
    db_langs = {
        code: cfg["gf_db_column"]
        for code, cfg in LANG_CONFIG.items()
        if cfg.get("gf_db_column")
    }

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cols = list(db_langs.values())
    cur.execute(f"SELECT fun_name, category, {', '.join(cols)} FROM functions")

    index = {}
    surface_index = {code: {} for code in db_langs if code != "en"}

    for row in cur.fetchall():
        fun_name, category = row[0], row[1]
        lins = {}
        for i, (lang_code, _) in enumerate(db_langs.items()):
            val = row[2 + i]
            if val and val.strip() and val != "variants {}":
                lins[lang_code] = val

        base = _extract_base_word(fun_name)
        entry = {"fun_name": fun_name, "category": category, "src_word": base, "lins": lins}
        index.setdefault(base, []).append(entry)

        eng_surface = extract_lin_surface(lins["en"]) if "en" in lins else None
        if eng_surface:
            for lang_code in surface_index:
                if lang_code in lins:
                    src_surface = extract_lin_surface(lins[lang_code])
                    if src_surface:
                        surface_index[lang_code].setdefault(src_surface.lower(), eng_surface)

    conn.close()
    return index, surface_index


def wordnet_lookup(english_words, wn_index):
    """
    Look up English words in the WordNet index.
    Returns (found_entries, missing_words).
    """
    print("3. Looking up words in GF WordNet database...")
    found_entries = []
    missing_words = {}
    seen_fun_names = set()

    for word, cat in english_words.items():
        key = re.sub(r"[^a-z0-9]", "_", word.lower())
        key = re.sub(r"_+", "_", key).strip("_")

        if key in wn_index:
            for e in wn_index[key]:
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
    translate from English to fill the gaps. Covers both languages without a
    gf_db_column and DB-configured languages whose entry has a NULL lin.
    """
    langs_needing_fill = [
        lang for lang in target_langs
        if LANG_CONFIG.get(lang) and lang != "en"
    ]
    if not langs_needing_fill:
        return

    print(f"  Filling missing lins via NMT for: {', '.join(langs_needing_fill)}")

    for lang in langs_needing_fill:
        to_translate = []
        for i, entry in enumerate(entries):
            if lang not in entry["lins"] and "en" in entry["lins"]:
                surface = extract_lin_surface(entry["lins"]["en"])
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


def build_generated_entries(missing_words, target_langs):
    """
    For words not found in WordNet, translate to each target language
    and construct GF entry dicts using simple paradigm calls.
    """
    if not missing_words:
        return []

    print(f"4. Generating entries for {len(missing_words)} words not in WordNet...")
    word_list = list(missing_words.keys())
    cat_list = [missing_words[w] for w in word_list]

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
            translations = lang_translations.get(lang, [])
            surface = translations[i] if i < len(translations) else ""
            if surface:
                lins[lang] = _make_lin_expr(surface, cat, lang)
        entries.append({"fun_name": fun_name, "category": cat, "src_word": word, "lins": lins})

    return entries
