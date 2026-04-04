import re

from .config import LANG_CONFIG
from .nmt import translate_batch


def _is_valid_translation(text):
    """Return False for garbage NMT output that shouldn't go into the grammar.

    NMT models sometimes produce degenerate output for short or malformed input:
    repeated tokens ("ng ng ng ng ..."), punctuation-only strings, or empty
    translations.  These are useless as GF lin expressions and would bloat the
    grammar with noise.

    Heuristic: reject if the unique-token ratio is below 0.4 for outputs longer
    than 4 tokens (catches "ng ng ng ..." style repetition loops).
    """
    if not text or not text.strip():
        return False
    tokens = text.split()
    if len(tokens) > 4 and len(set(tokens)) / len(tokens) < 0.4:
        return False
    return True


def _make_fun_name(english_word, gf_cat):
    """Create a valid GF identifier from an English word and GF category."""
    normalized = re.sub(r"[^a-z0-9]", "_", english_word.lower())
    normalized = re.sub(r"_+", "_", normalized).strip("_") or "unknown"
    if normalized[0].isdigit():
        normalized = f"n_{normalized}"
    return f"{normalized}_{gf_cat}"


def _make_lin_expr(surface_form, gf_cat, lang_code):
    """
    Generate a minimal RGL paradigm call for a surface form.

    For full-morphology languages (gf_zero_morph=False), verbs must be
    wrapped: mkV2 (mkV "run") — the outer mkV2 adds the valency frame.
    For zero-morphology languages (gf_zero_morph=True, e.g. Japanese),
    a flat mkN/mkV2/... call is used since there are no inflection tables.

    If the surface form does not satisfy the language's verb paradigm
    requirements (e.g. Spanish mkV requires an -ar/-ir/-er infinitive),
    returns "variants {}" so the entry compiles but has no realisation.
    """
    # GF paradigm functions (mkN, mkV, mkA, ...) require a single word — a
    # multi-word translation cannot be passed directly and would cause a GF
    # compile error.  Fall back to variants {} so the entry compiles cleanly.
    if " " in surface_form:
        return "variants {}"
    w = surface_form.replace('"', '\\"')
    cfg = LANG_CONFIG[lang_code]
    if cfg["gf_zero_morph"]:
        fn = {"V2": "mkV2", "V": "mkV", "A": "mkA", "Adv": "mkAdv", "PN": "mkPN"}.get(gf_cat, "mkN")
        return f'{fn} "{w}"'
    else:
        if gf_cat in ("V2", "V"):
            verb_suffixes = cfg.get("gf_verb_suffixes")
            if verb_suffixes and not surface_form.endswith(verb_suffixes):
                return "variants {}"
        if gf_cat == "V2":
            return f'mkV2 (mkV "{w}")'
        fn = {"V": "mkV", "A": "mkA", "Adv": "mkAdv", "PN": "mkPN"}.get(gf_cat, "mkN")
        return f'{fn} "{w}"'


def extract_lin_surface(lin_expr):
    """Extract the first quoted surface form from a GF lin expression.

    Examples:
        mkN "tree"          → "tree"
        mkV2 (mkV "run")    → "run"
        variants {}         → None
    """
    m = re.search(r'"([^"]+)"', lin_expr)
    return m.group(1) if m else None


def fill_missing_lins(entries, target_langs, source_lang=None):
    """
    For Wiktionary entries that have some lins but are missing others, fill
    gaps via NMT.

    Bridge language selection — avoids unnecessary English round-trips:
      1. If source_lang lin is present and source_lang ≠ target_lang, translate
         source_lang → target_lang directly.
      2. Otherwise fall back to the English lin as the bridge.

    Only called for wikt_entries — generated entries have all lins built by
    build_generated_entries, and WordNet entries are handled by Parse.pgf
    at runtime without needing explicit lins here.
    """
    langs_needing_fill = [
        lang for lang in target_langs
        if LANG_CONFIG.get(lang) and lang != "en"
    ]
    if not langs_needing_fill:
        return

    print(f"  Filling missing lins via NMT for: {', '.join(langs_needing_fill)}")

    for lang in langs_needing_fill:
        by_bridge: dict = {}
        for i, entry in enumerate(entries):
            if lang in entry["lins"]:
                continue
            if source_lang and source_lang != lang and source_lang in entry["lins"]:
                bridge = source_lang
            elif "en" in entry["lins"]:
                bridge = "en"
            else:
                continue
            surface = extract_lin_surface(entry["lins"][bridge])
            if surface:
                by_bridge.setdefault(bridge, []).append((i, surface, entry["category"]))

        for bridge, items in by_bridge.items():
            words = [item[1] for item in items]
            try:
                translated = translate_batch(words, bridge, lang)
                for (idx, _, cat), trans_word in zip(items, translated):
                    if _is_valid_translation(trans_word):
                        entries[idx]["lins"][lang] = _make_lin_expr(trans_word, cat, lang)
            except Exception as e:
                print(f"  Warning: fill translation {bridge}→{lang} failed: {e}")


def build_generated_entries(missing_words, target_langs, source_lang=None):
    """
    For words not found anywhere in the lookup chain, build GF entries by
    translating surface forms to each target language via NMT.

    missing_words : {source_surface: gf_cat}
                    Always keyed by the source-language surface form.
    source_lang   : original source language if not English. When provided,
                    translations go source → target directly instead of
                    English → target, avoiding the English bridge.
    """
    if not missing_words:
        return []

    print(f"  Generating entries for {len(missing_words)} words not in WordNet...")
    word_list = list(missing_words.keys())
    cat_list = [missing_words[w] for w in word_list]

    use_direct = bool(source_lang and source_lang != "en")

    lang_translations = {}
    for lang in target_langs:
        if lang == source_lang:
            # Source-language surface is already known — no translation needed
            lang_translations[lang] = word_list
        elif use_direct and source_lang:
            print(f"   Translating to {lang.upper()} (from {source_lang.upper()})...")
            try:
                lang_translations[lang] = translate_batch(word_list, source_lang, lang)
            except Exception as e:
                print(f"   Warning: translation {source_lang}→{lang} failed: {e}")
                lang_translations[lang] = [""] * len(word_list)
        else:
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
            if surface and _is_valid_translation(surface):
                lins[lang] = _make_lin_expr(surface, cat, lang)
        entries.append({"fun_name": fun_name, "category": cat, "src_word": word, "lins": lins})

    return entries
