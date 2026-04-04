"""
Lesson generation module.

Given a vocabulary dict {word: gf_cat} extracted from a source document,
produces structured LessonEntry dicts containing:

  - Word translations in each language (from GF linearization)
  - Systematically generated example sentences across tenses, persons,
    and polarities — all produced by GF, always grammatically correct
  - Source examples: verbatim sentences from the document containing
    the word (translations left to the caller/app layer)

All generated sentence content comes from GF linearization against
Parse.pgf (the pre-compiled GF WordNet grammar). No NMT is used here.

Usage:
    from translator import build_lesson
    entries = build_lesson(
        vocab={"battery": "N", "charge": "V2", "fast": "A"},
        source_text=open("doc.srt").read(),
        source_lang="en",
        target_langs=["es", "de"],
    )
"""

import dataclasses
import re
from collections import Counter
from typing import Optional

import pgf

from .config import LANG_CONFIG
from .pattern import analyze_tree as _analyze_tree, GrammarPattern, _compute_difficulty
from .pipeline import _load_parse_grammar, _suppress_c_stdout
from .keywords import _get_nlp

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Utility V2 verbs confirmed present in Parse.pgf — used in N sentence patterns.
# have_10_V2 is used because it maps to "haben" in German (sense 2 maps to "sein").
_UTILITY_V2 = ["have_10_V2", "see_1_V2", "need_2_V2", "use_1_V2"]

# Generic nouns used as objects/placeholders in templates
_GENERIC_N = "thing_1_N"

# Utility V verbs used in Adv sentence patterns
_UTILITY_V_FOR_ADV = ["run_1_V", "speak_1_V", "walk_1_V"]

# Pronouns: {label: GF_Pron_function}
_PRONOUNS = {
    "I":    "i_Pron",
    "you":  "youSg_Pron",
    "he":   "he_Pron",
    "she":  "she_Pron",
    "we":   "we_Pron",
    "they": "they_Pron",
    "it":   "it_Pron",
}

# Tense+aspect pairs used when enumerating candidate patterns.
# Order matters: simpler pairs first so low-n selections favour them.
_TENSE_ASPECT_PAIRS = [
    ("TPres", "ASimul"),
    ("TPast", "ASimul"),
    ("TFut",  "ASimul"),
    ("TCond", "ASimul"),
    ("TPres", "AAnter"),
    ("TPast", "AAnter"),
]

# Persons used when enumerating declarative clause candidates.
# "it_Pron" is excluded here — handled specifically for N/A copula patterns.
_GENERATION_PERSONS = ["i_Pron", "youSg_Pron", "he_Pron", "they_Pron"]
_QUESTION_PERSONS   = ["i_Pron", "youSg_Pron"]

# GF category suffix used in function names
_CAT_SUFFIXES = {
    "N":   ("_N",),
    "V":   ("_V",),
    "V2":  ("_V2",),
    "A":   ("_A",),
    "Adv": ("_Adv",),
}

# Detect unresolved GF linearizations: they appear as [FunctionName]
_BRACKET_RE = re.compile(r'\[')

# Sentences longer than this are excluded from source examples
_MAX_EXAMPLE_LEN = 300
# Max source sentences to attempt to parse during sense selection
_MAX_PARSE_SENTS = 3
# Max source example sentences to include per word
_MAX_EXAMPLES = 3


# ---------------------------------------------------------------------------
# Safe linearization helpers
# ---------------------------------------------------------------------------

def _lin_safe(concretes: dict, tree_str: str) -> Optional[dict]:
    """
    Build a GF expression from tree_str and linearize it in all concretes.

    Returns {lang_code: text} for every language that linearizes cleanly
    (non-empty, no bracket markers).  Languages with missing or incomplete
    linearizations are omitted from the result rather than failing the call.
    Returns None only if the expression cannot be parsed or nothing succeeds.

    This allows languages with sparser WordNet coverage (e.g. Japanese) to
    coexist with fully-covered languages without blocking sense selection or
    sentence generation for the languages that do work.
    """
    try:
        expr = pgf.readExpr(tree_str)
    except Exception:
        return None

    result = {}
    for lang, concrete in concretes.items():
        try:
            lin = concrete.linearize(expr)
        except Exception:
            continue
        if lin and not _BRACKET_RE.search(lin):
            result[lang] = lin

    return result if result else None


def _bare_word(concretes: dict, fn: str, gf_cat: str) -> dict:
    """
    Linearize the bare vocabulary item in each language.

    For N: UseN — gives the nominative singular form.
    For V/V2: bare fn — gives the infinitive/stem form the language uses.
    For A: PositA — gives the base adjective form.
    For Adv: bare fn.

    Results are cached in morph_cache (in-process, optionally SQLite-backed)
    so repeated calls for the same GF function skip the C library entirely.
    """
    from .morph_cache import get as _mc_get, put as _mc_put

    # The tabular representation gives us language-specific dictionary forms:
    # For verbs: 's (VInf False)' (German pure infinitive without 'zu'),
    #            'inf' (English), etc.
    # For nouns: 's Sg Nom' (nominative singular — the dictionary form).
    # For adjectives: 's Masc Sg Nom' (positive base form) or similar.
    # Fall back to linearize() if the expected key is absent.
    # V uses bare fn → 's (VInf False)' in German, 'inf' in English, 'p' in Spanish
    # V2 uses SlashV2a fn → 's s (VInf False)' in German (extra 's s' prefix)
    _V_INF_KEYS = ('inf', 's (VInf False)', 's s (VInf False)', 'p')  # English, German, V2-German, Spanish
    _N_SG_KEYS = ('s Sg Nom', 's Sg')
    _A_PRED_KEY = 's APred'

    if gf_cat == "N":
        base_tree = f"UseN {fn}"
    elif gf_cat == "V":
        base_tree = fn
    elif gf_cat == "V2":
        base_tree = f"SlashV2a {fn}"
    elif gf_cat == "A":
        base_tree = f"PositA {fn}"
    else:
        base_tree = fn

    result = {}
    langs_needed = []
    for lang in concretes:
        cached = _mc_get(fn, gf_cat, lang)
        if cached is not None:
            result[lang] = cached
        else:
            langs_needed.append(lang)

    if not langs_needed:
        return result

    # Parse the expression once for all remaining languages
    try:
        expr = pgf.readExpr(base_tree)
    except Exception:
        return result

    for lang in langs_needed:
        concrete = concretes[lang]
        word = None
        # Try tabularLinearize for the cleanest dictionary form
        try:
            table = concrete.tabularLinearize(expr)
            if gf_cat in ("V", "V2"):
                for key in _V_INF_KEYS:
                    if table.get(key) and not _BRACKET_RE.search(table[key]):
                        word = table[key]
                        break
            elif gf_cat == "N":
                for key in _N_SG_KEYS:
                    if table.get(key) and not _BRACKET_RE.search(table[key]):
                        word = table[key]
                        break
            elif gf_cat == "A":
                if table.get(_A_PRED_KEY) and not _BRACKET_RE.search(table[_A_PRED_KEY]):
                    word = table[_A_PRED_KEY]
        except Exception:
            pass

        # Fall back to plain linearize if tabular didn't give us a clean word
        if not word:
            try:
                lin = concrete.linearize(expr)
                if lin and not _BRACKET_RE.search(lin):
                    word = lin
            except Exception:
                pass

        if word:
            result[lang] = word
            _mc_put(fn, gf_cat, lang, word)

    return result


# ---------------------------------------------------------------------------
# Sense selection
# ---------------------------------------------------------------------------

def _extract_sense_number(fn_name: str) -> int:
    """
    Extract the numeric sense index from a GF function name.
    "charge_10_N" → 10, "chargeFem_7_N" → 7, "charge_off_V" → 999.
    """
    m = re.search(r'_(\d+)_[A-Za-z0-9]+$', fn_name)
    return int(m.group(1)) if m else 999


def _collect_fns(expr) -> list:
    """Walk a GF parse tree and collect all leaf function names."""
    found = []
    _walk(expr, found)
    return found


def _walk(expr, found: list):
    try:
        name, args = expr.unpack()
    except Exception:
        return
    if name and '_' in name and name[0].islower():
        found.append(name)
    for a in args:
        _walk(a, found)


def _cat_matches(fn_name: str, gf_cat: str) -> bool:
    suffixes = _CAT_SUFFIXES.get(gf_cat, ())
    return any(fn_name.endswith(s) for s in suffixes)


def _minimal_tree(fn: str, gf_cat: str) -> str:
    """Return the minimal sentence tree for testing if a sense linearizes."""
    if gf_cat == "N":
        return f"PhrUtt NoPConj (UttNP (DetCN (DetQuant DefArt NumSg) (UseN {fn}))) NoVoc"
    elif gf_cat == "V":
        return (f"PhrUtt NoPConj (UttS (PredVPS (UsePron i_Pron) "
                f"(MkVPS (TTAnt TPres ASimul) PPos (UseV {fn})))) NoVoc")
    elif gf_cat == "V2":
        return (f"PhrUtt NoPConj (UttS (PredVPS (UsePron i_Pron) "
                f"(MkVPS (TTAnt TPres ASimul) PPos "
                f"(ComplSlash (SlashV2a {fn}) (UsePron it_Pron))))) NoVoc")
    elif gf_cat == "A":
        return (f"PhrUtt NoPConj (UttS (PredVPS (UsePron it_Pron) "
                f"(MkVPS (TTAnt TPres ASimul) PPos (UseComp (CompAP (PositA {fn})))))) NoVoc")
    else:  # Adv
        return f"PhrUtt NoPConj (UttAdv {fn}) NoVoc"


def _rank_all_senses(
    word: str,
    gf_cat: str,
    src_concrete,
    sentences_with_word: list,
    grammar,
    all_concretes: dict,
) -> tuple:
    """
    Return (ordered_candidates, boost) for all lookupMorpho results matching
    gf_cat (with V/V2 sibling fallback).

    ordered_candidates : list of fn names sorted best-first (sense number,
                         boosted by source-parse frequency).
    boost              : Counter {fn: n_source_sentences_it_appeared_in}.
    """
    src_lang = _get_lang_for_concrete(src_concrete, grammar)
    slow_parse = (src_lang is not None and
                  LANG_CONFIG.get(src_lang, {}).get("slow_source_parse", False))

    try:
        with _suppress_c_stdout():
            morpho_results = list(src_concrete.lookupMorpho(word))
    except Exception:
        return [], Counter()

    seen: set = set()
    candidates: list = []
    for fn_name, _tag, _prob in morpho_results:
        if fn_name not in seen and _cat_matches(fn_name, gf_cat):
            seen.add(fn_name)
            candidates.append(fn_name)

    # V/V2 sibling fallback
    if not candidates and gf_cat == "V2":
        for fn_name, _tag, _prob in morpho_results:
            if fn_name not in seen and _cat_matches(fn_name, "V"):
                seen.add(fn_name)
                candidates.append(fn_name)
    elif not candidates and gf_cat == "V":
        for fn_name, _tag, _prob in morpho_results:
            if fn_name not in seen and _cat_matches(fn_name, "V2"):
                seen.add(fn_name)
                candidates.append(fn_name)

    if not candidates:
        return [], Counter()

    candidates.sort(key=_extract_sense_number)

    # Phase 1: parse source sentences to build a frequency boost counter.
    # Skipped for German (ParseGer is slow, ~15s/sentence).
    boost: Counter = Counter()
    if not slow_parse and sentences_with_word:
        candidate_set = set(candidates)
        for sent in sentences_with_word[:_MAX_PARSE_SENTS]:
            try:
                with _suppress_c_stdout():
                    it = src_concrete.parse(sent)
                    pair = next(it)
                    del it
                _, expr = pair
                for fn in _collect_fns(expr):
                    if fn in candidate_set:
                        boost[fn] += 1
            except (StopIteration, pgf.ParseError, Exception):
                pass

    # Stable-sort: primary key = sense number (lower = more common WordNet sense),
    # secondary key = negative parse frequency (higher frequency = earlier).
    # Cap the boost effect to ±3 sense-number bands.
    def _rank(fn):
        sense_num = _extract_sense_number(fn)
        parse_hits = boost.get(fn, 0)
        promoted = max(0, sense_num - min(3, parse_hits))
        return (promoted, -parse_hits)

    ordered = sorted(candidates, key=_rank)
    return ordered, boost


def _pick_primary(
    ordered: list,
    gf_cat: str,
    all_concretes: dict,
    word: str,
    src_lang: Optional[str],
) -> Optional[str]:
    """
    From a pre-ranked candidate list, return the first fn that linearizes
    cleanly in all concretes and whose target translations differ from the
    source word surface form.  Falls back to first-that-linearizes if all
    senses translate identically to the source word (e.g. proper nouns).
    """
    src_word_lower = word.lower()
    non_src_langs = [l for l in all_concretes if l != src_lang]

    for fn in ordered:
        lins = _lin_safe(all_concretes, _minimal_tree(fn, gf_cat))
        if lins is None:
            continue
        if non_src_langs:
            all_same = all(lins.get(l, "").lower() == src_word_lower
                           for l in non_src_langs)
            if all_same:
                continue
        return fn

    # Fallback: accept same-as-source translations
    for fn in ordered:
        if _lin_safe(all_concretes, _minimal_tree(fn, gf_cat)) is not None:
            return fn

    return None


def _build_alternates(
    gf_cat: str,
    primary_fn: Optional[str],
    ordered: list,
    boost: Counter,
    all_concretes: dict,
    src_lang: Optional[str],
) -> list:
    """
    Return a list of alternate-sense dicts for senses other than primary_fn.

    Each dict:
        gf_function   : str
        translations  : {lang: str}   bare-word translation per language
        source_count  : int           times this sense appeared in source parses

    Senses whose target-language translations are identical to the primary
    sense are skipped (showing duplicates adds noise, not value).
    """
    # Fingerprint of primary translations for dedup
    seen_fps: set = set()
    if primary_fn:
        primary_trans = _bare_word(all_concretes, primary_fn, gf_cat)
        fp = _translation_fingerprint(primary_trans, src_lang)
        seen_fps.add(fp)

    alternates = []
    for fn in ordered:
        if fn == primary_fn:
            continue
        if _lin_safe(all_concretes, _minimal_tree(fn, gf_cat)) is None:
            continue
        translations = _bare_word(all_concretes, fn, gf_cat)
        fp = _translation_fingerprint(translations, src_lang)
        if fp in seen_fps:
            continue
        seen_fps.add(fp)
        alternates.append({
            "gf_function": fn,
            "translations": translations,
            "source_count": boost.get(fn, 0),
        })

    return alternates


def _translation_fingerprint(translations: dict, src_lang: Optional[str]) -> tuple:
    """Tuple of (lang, word.lower()) for non-source languages — used for dedup."""
    return tuple(sorted(
        (l, w.lower()) for l, w in translations.items() if l != src_lang
    ))


def select_best_sense(
    word: str,
    gf_cat: str,
    src_concrete,
    sentences_with_word: list,
    grammar,
    all_concretes: dict,
) -> Optional[str]:
    """
    Convenience wrapper: rank all senses and return the single best fn.
    For the full ranked list + boost counter (needed to build alternates),
    call _rank_all_senses + _pick_primary directly.
    """
    ordered, _boost = _rank_all_senses(
        word, gf_cat, src_concrete, sentences_with_word, grammar, all_concretes
    )
    src_lang = _get_lang_for_concrete(src_concrete, grammar)
    return _pick_primary(ordered, gf_cat, all_concretes, word, src_lang)


def _get_lang_for_concrete(concrete, grammar) -> Optional[str]:
    """Reverse-lookup: find the language code for a concrete grammar."""
    for lang_code, cfg in LANG_CONFIG.items():
        suffix = cfg.get("gf_suffix", "")
        name = f"Parse{suffix}"
        if grammar.languages.get(name) is concrete:
            return lang_code
    return None


# ---------------------------------------------------------------------------
# Sentence generation per GF category
# ---------------------------------------------------------------------------

def _sentence(label: str, concretes: dict, tree: str) -> Optional[dict]:
    """Build a sentence dict if the tree linearizes in at least one concrete."""
    lins = _lin_safe(concretes, tree)
    if lins is None:
        return None
    try:
        pattern = dataclasses.asdict(_analyze_tree(tree))
    except Exception:
        pattern = {}
    return {"label": label, "tree": tree, "pattern": pattern, **lins}


# ---------------------------------------------------------------------------
# Pattern-driven sentence generation
# ---------------------------------------------------------------------------

def _candidate_clause_patterns(cat: str) -> list:
    """
    Enumerate all valid clause-level GrammarPattern instances for a GF category.

    This is the "universe" of patterns that profile-based selection draws from.
    NP-fragment patterns (UttNP) for N and A are handled as fixed baselines in
    generate_sentences() and are not included here.
    """
    patterns = []

    if cat in ("V", "V2"):
        verb_cat = "UseV" if cat == "V" else "SlashV2a"
        for tense, aspect in _TENSE_ASPECT_PAIRS:
            for polarity in ("PPos", "PNeg"):
                for person in _GENERATION_PERSONS:
                    d = _compute_difficulty("UttS", tense, aspect, polarity, person, False)
                    patterns.append(GrammarPattern(
                        utt_type="UttS", tense=tense, aspect=aspect,
                        polarity=polarity, person=person, verb_cat=verb_cat,
                        progressive=False, attributive=False, difficulty=d,
                    ))
                    if aspect == "ASimul":
                        d = _compute_difficulty("UttS", tense, aspect, polarity, person, True)
                        patterns.append(GrammarPattern(
                            utt_type="UttS", tense=tense, aspect=aspect,
                            polarity=polarity, person=person, verb_cat=verb_cat,
                            progressive=True, attributive=False, difficulty=d,
                        ))
                for person in _QUESTION_PERSONS:
                    d = _compute_difficulty("UttQS", tense, aspect, polarity, person, False)
                    patterns.append(GrammarPattern(
                        utt_type="UttQS", tense=tense, aspect=aspect,
                        polarity=polarity, person=person, verb_cat=verb_cat,
                        progressive=False, attributive=False, difficulty=d,
                    ))

    if cat in ("V", "V2"):
        verb_cat = "UseV" if cat == "V" else "SlashV2a"

        # German V-S inversion patterns (word_order="inv").
        # Same tense/aspect/polarity/person combinations as SVO, but fronted.
        # Difficulty is +1 vs equivalent SVO pattern (PT Stage 4).
        for tense, aspect in [("TPres", "ASimul"), ("TPast", "ASimul"),
                               ("TFut", "ASimul"), ("TPres", "AAnter")]:
            for polarity in ("PPos", "PNeg"):
                for person in _GENERATION_PERSONS:
                    d = _compute_difficulty("UttS", tense, aspect, polarity,
                                            person, False, word_order="inv")
                    patterns.append(GrammarPattern(
                        utt_type="UttS", tense=tense, aspect=aspect,
                        polarity=polarity, person=person, verb_cat=verb_cat,
                        progressive=False, attributive=False, difficulty=d,
                        word_order="inv",
                    ))

        # German verb-final patterns (word_order="v_end").
        # Embedded clause with fixed "he_Pron" subject ("Ich weiß, dass er…").
        # Difficulty is +2 vs equivalent SVO pattern (PT Stage 5).
        for tense, aspect in [("TPres", "ASimul"), ("TPast", "ASimul")]:
            for polarity in ("PPos", "PNeg"):
                d = _compute_difficulty("UttS", tense, aspect, polarity,
                                        "he_Pron", False, word_order="v_end")
                patterns.append(GrammarPattern(
                    utt_type="UttS", tense=tense, aspect=aspect,
                    polarity=polarity, person="he_Pron", verb_cat=verb_cat,
                    progressive=False, attributive=False, difficulty=d,
                    word_order="v_end",
                ))

        # Japanese passive patterns (voice="Pass") — V2 only.
        if cat == "V2":
            for tense, aspect in [("TPres", "ASimul"), ("TPast", "ASimul")]:
                for polarity in ("PPos", "PNeg"):
                    for person in ("i_Pron", "he_Pron"):
                        d = _compute_difficulty("UttS", tense, aspect, polarity,
                                                person, False, voice="Pass")
                        patterns.append(GrammarPattern(
                            utt_type="UttS", tense=tense, aspect=aspect,
                            polarity=polarity, person=person, verb_cat="SlashV2a",
                            progressive=False, attributive=False, difficulty=d,
                            voice="Pass",
                        ))

    elif cat == "N":
        for verb_cat, persons in [
            ("UseComp",  ["it_Pron", "i_Pron", "youSg_Pron"]),
            ("SlashV2a", ["i_Pron",  "youSg_Pron", "they_Pron"]),
        ]:
            for tense, aspect in _TENSE_ASPECT_PAIRS:
                for polarity in ("PPos", "PNeg"):
                    for person in persons:
                        d = _compute_difficulty("UttS", tense, aspect, polarity, person, False)
                        patterns.append(GrammarPattern(
                            utt_type="UttS", tense=tense, aspect=aspect,
                            polarity=polarity, person=person, verb_cat=verb_cat,
                            progressive=False, attributive=False, difficulty=d,
                        ))

    elif cat == "A":
        for tense, aspect in _TENSE_ASPECT_PAIRS:
            for polarity in ("PPos", "PNeg"):
                for person in ["it_Pron", "i_Pron", "youSg_Pron"]:
                    d = _compute_difficulty("UttS", tense, aspect, polarity, person, False)
                    patterns.append(GrammarPattern(
                        utt_type="UttS", tense=tense, aspect=aspect,
                        polarity=polarity, person=person, verb_cat="UseComp",
                        progressive=False, attributive=False, difficulty=d,
                    ))

    return list(dict.fromkeys(patterns))


def select_generation_patterns(
    cat: str,
    profile,           # SkillProfile | None
    source_patterns,   # Counter[GrammarPattern] | None
    n: int = 15,
    target_lang: Optional[str] = None,
) -> list:
    """
    Choose which GrammarPatterns to generate sentences for.

    Strategy
    --------
    1. Enumerate all valid patterns for the category.
    2. Clamp to difficulty ≤ current_level + 2 (min ceiling = 2 for new learners).
    3. For German: apply a hard PT-stage ceiling — patterns whose word-order
       requirements exceed the learner's current Processability Theory stage
       are excluded.  This prevents generating structures the learner cannot
       yet process (see Pienemann's Teachability Hypothesis).
    4. Within each difficulty bucket, rank by source-document frequency so that
       structures the learner will actually encounter are preferred.
    5. Allocate n slots proportionally to recommend_difficulty_mix(), drawing
       from each difficulty bucket in turn.  Any shortfall (a bucket has fewer
       candidates than its allocation) is backfilled from the next bucket.

    Source frequency can boost priority *within* the allowed difficulty range but
    cannot raise a pattern above the ceiling — the learner's level is the
    primary constraint.
    """
    candidates = _candidate_clause_patterns(cat)
    if not candidates:
        return []

    if profile is None:
        max_diff = 2
        mix: dict = {1: 0.40, 2: 0.60}
    else:
        max_diff = min(5, profile.current_level() + 2)
        mix = profile.recommend_difficulty_mix()

    candidates = [p for p in candidates if p.difficulty <= max_diff]

    # Japanese: ProgrVP is not supported by ParseJpn — produces bracketed output.
    # Filter progressive patterns when Japanese is the target to avoid empty sentences.
    if target_lang == "ja":
        candidates = [p for p in candidates if not p.progressive]

    # German PT stage ceiling — exclude structures the learner cannot yet process.
    # Current pattern builder only generates SVO main clauses, so this primarily
    # gates Konjunktiv II (TCond, PT requires B2 grammar not just word-order) and
    # perfect aspect (Partizip II, PT Stage 3+).
    if target_lang == "de" and profile is not None:
        pt_stage = profile.de_pt_stage()
        filtered = []
        for p in candidates:
            # Partizip II (Perfekt) requires separable-prefix awareness — PT Stage 3+
            if p.aspect == "AAnter" and pt_stage < 3:
                continue
            # Konjunktiv II also sits at B2 and shouldn't appear before Stage 3
            if p.tense == "TCond" and pt_stage < 3:
                continue
            # V-S inversion: PT Stage 4
            if p.word_order == "inv" and pt_stage < 4:
                continue
            # Verb-final subordinate clause: PT Stage 5
            if p.word_order == "v_end" and pt_stage < 5:
                continue
            filtered.append(p)
        candidates = filtered

    # Bucket candidates by difficulty; within each bucket rank by combined signal:
    # source-document frequency + node-weakness score from the skill profile.
    from .nodes import node_weakness_score as _node_weakness_score

    def _freq(p: GrammarPattern) -> float:
        src  = source_patterns.get(p, 0) if source_patterns else 0
        node = _node_weakness_score(p, profile, target_lang or "") if profile else 0.0
        return src + node

    buckets: dict = {}
    for p in candidates:
        buckets.setdefault(p.difficulty, []).append(p)
    for diff in buckets:
        buckets[diff].sort(key=_freq, reverse=True)

    # Proportional allocation: primary level first, then remainder backfill.
    sorted_mix = sorted(mix.items(), key=lambda kv: -kv[1])  # primary level first
    result: list = []
    allocated = 0

    for i, (diff, frac) in enumerate(sorted_mix):
        pool = buckets.get(diff, [])
        if i < len(sorted_mix) - 1:
            want = round(frac * n)
        else:
            want = n - allocated          # give remainder to last bucket
        take = pool[:want]
        result.extend(take)
        allocated += len(take)

    # Backfill: if allocations came up short, pull from any remaining candidates.
    if allocated < n:
        used = set(id(p) for p in result)
        for p in candidates:
            if len(result) >= n:
                break
            if id(p) not in used:
                result.append(p)

    return result[:n]


def _pattern_to_tree(pattern: GrammarPattern, fn: str, cat: str) -> Optional[str]:
    """
    Build a GF abstract syntax tree string from a GrammarPattern and GF function.

    Returns None if the pattern is not expressible for this category.
    """
    tense    = pattern.tense    or "TPres"
    aspect   = pattern.aspect   or "ASimul"
    polarity = pattern.polarity or "PPos"
    person   = pattern.person   or "i_Pron"
    ta = f"(TTAnt {tense} {aspect})"

    # --- Non-default structural variants (word_order / voice) ---
    # These must come before the category dispatch because V/V2 return early.

    if pattern.word_order == "inv":
        # Fronted adverb triggers V-S inversion in German automatically via AdvS.
        # here_1_Adv is confirmed present in gf-wordnet Parse.pgf.
        adv = "here_1_Adv"
        if cat == "V":
            vp = f"(UseV {fn})"
            return (f"PhrUtt NoPConj (UttS (AdvS {adv} (PredVPS (UsePron {person}) "
                    f"(MkVPS {ta} {polarity} {vp})))) NoVoc")
        if cat == "V2":
            inner = f"(ComplSlash (SlashV2a {fn}) (UsePron it_Pron))"
            return (f"PhrUtt NoPConj (UttS (AdvS {adv} (PredVPS (UsePron {person}) "
                    f"(MkVPS {ta} {polarity} {inner})))) NoVoc")
        return None

    if pattern.word_order == "v_end":
        # Matrix "I know that…" + embedded clause with vocabulary verb.
        # ComplVS know_1_VS S: "know" embeds the subordinate S.
        # German linearization puts the embedded verb last automatically.
        if cat == "V":
            emb_vp = f"(UseV {fn})"
            emb = f"(PredVPS (UsePron {person}) (MkVPS {ta} {polarity} {emb_vp}))"
            return (f"PhrUtt NoPConj (UttS (PredVPS (UsePron i_Pron) "
                    f"(MkVPS (TTAnt TPres ASimul) PPos "
                    f"(ComplVS know_1_VS {emb})))) NoVoc")
        if cat == "V2":
            emb_vp = f"(ComplSlash (SlashV2a {fn}) (UsePron it_Pron))"
            emb = f"(PredVPS (UsePron {person}) (MkVPS {ta} {polarity} {emb_vp}))"
            return (f"PhrUtt NoPConj (UttS (PredVPS (UsePron i_Pron) "
                    f"(MkVPS (TTAnt TPres ASimul) PPos "
                    f"(ComplVS know_1_VS {emb})))) NoVoc")
        return None

    if pattern.voice == "Pass" and cat == "V2":
        # PassVPSlash (SlashV2a fn): passive voice without explicit agent.
        # Japanese: produces られる/れる form. Other languages: standard passive.
        return (f"PhrUtt NoPConj (UttS (PredVPS (UsePron {person}) "
                f"(MkVPS {ta} {polarity} "
                f"(PassVPSlash (SlashV2a {fn}))))) NoVoc")

    if cat == "V":
        vp = (f"(ProgrVP (UseV {fn}))" if pattern.progressive
              else f"(UseV {fn})")
        if pattern.utt_type == "UttQS":
            return (f"PhrUtt NoPConj (UttQS (UseQCl {ta} {polarity} "
                    f"(QuestCl (PredVP (UsePron {person}) (UseV {fn}))))) NoVoc")
        if pattern.utt_type == "UttS":
            return (f"PhrUtt NoPConj (UttS (PredVPS (UsePron {person}) "
                    f"(MkVPS {ta} {polarity} {vp}))) NoVoc")

    elif cat == "V2":
        inner = f"(ComplSlash (SlashV2a {fn}) (UsePron it_Pron))"
        vp    = f"(ProgrVP {inner})" if pattern.progressive else inner
        if pattern.utt_type == "UttQS":
            return (f"PhrUtt NoPConj (UttQS (UseQCl {ta} {polarity} "
                    f"(QuestCl (PredVP (UsePron {person}) {inner})))) NoVoc")
        if pattern.utt_type == "UttS":
            return (f"PhrUtt NoPConj (UttS (PredVPS (UsePron {person}) "
                    f"(MkVPS {ta} {polarity} {vp}))) NoVoc")

    elif cat == "N":
        obj = f"(DetCN (DetQuant IndefArt NumSg) (UseN {fn}))"
        if pattern.verb_cat == "UseComp":
            return (f"PhrUtt NoPConj (UttS (PredVPS (UsePron {person}) "
                    f"(MkVPS {ta} {polarity} (UseComp (CompNP {obj}))))) NoVoc")
        if pattern.verb_cat == "SlashV2a":
            return (f"PhrUtt NoPConj (UttS (PredVPS (UsePron {person}) "
                    f"(MkVPS {ta} {polarity} "
                    f"(ComplSlash (SlashV2a have_10_V2) {obj})))) NoVoc")

    elif cat == "A":
        if pattern.utt_type == "UttS" and pattern.verb_cat == "UseComp":
            return (f"PhrUtt NoPConj (UttS (PredVPS (UsePron {person}) "
                    f"(MkVPS {ta} {polarity} "
                    f"(UseComp (CompAP (PositA {fn})))))) NoVoc")

    return None


def generate_sentences(
    fn: str,
    cat: str,
    concretes: dict,
    patterns: list,
) -> list:
    """
    Generate sentence dicts for a GF function given a list of GrammarPatterns.

    Fixed baseline patterns (NP fragments, bare adverb, attributive adjective)
    are always prepended — they are the simplest demonstrations of the word and
    require no tense or person knowledge.  Profile-driven clause patterns follow.
    """
    sentences = []

    def s(label, tree):
        r = _sentence(label, concretes, tree)
        if r:
            sentences.append(r)

    # --- Fixed baselines (category-specific, always included) ---
    if cat == "N":
        s("the [word]",
          f"PhrUtt NoPConj (UttNP (DetCN (DetQuant DefArt NumSg) (UseN {fn}))) NoVoc")
        s("a [word]",
          f"PhrUtt NoPConj (UttNP (DetCN (DetQuant IndefArt NumSg) (UseN {fn}))) NoVoc")
        s("[word]s (plural)",
          f"PhrUtt NoPConj (UttNP (DetCN (DetQuant DefArt NumPl) (UseN {fn}))) NoVoc")

    elif cat == "A":
        s("the [word] thing",
          f"PhrUtt NoPConj (UttNP (DetCN (DetQuant DefArt NumSg) "
          f"(AdjCN (PositA {fn}) (UseN {_GENERIC_N})))) NoVoc")

    elif cat == "Adv":
        s("[Adv] (bare form)",
          f"PhrUtt NoPConj (UttAdv {fn}) NoVoc")
        for v_fn in _UTILITY_V_FOR_ADV:
            s("I [v] [Adv]",
              f"PhrUtt NoPConj (UttS (PredVPS (UsePron i_Pron) "
              f"(MkVPS (TTAnt TPres ASimul) PPos (AdvVP (UseV {v_fn}) {fn})))) NoVoc")
            if sentences and sentences[-1].get("label") == "I [v] [Adv]":
                break

    # --- Profile-driven clause patterns ---
    seen_trees = {r["tree"] for r in sentences}
    for pattern in patterns:
        tree = _pattern_to_tree(pattern, fn, cat)
        if tree is None or tree in seen_trees:
            continue
        seen_trees.add(tree)
        r = _sentence(pattern.label, concretes, tree)
        if r:
            sentences.append(r)

    # --- Japanese plain register variants ---
    # Emitted when Japanese is one of the target languages.  Uses tabularLinearize
    # to extract plain (dictionary) form conjugations from ParseJpn, paired with
    # polite-form translations in other languages for context.
    if "ja" in concretes:
        sentences.extend(_japanese_plain_sentences(fn, cat, concretes))

    return sentences


def _japanese_plain_sentences(fn: str, cat: str, concretes: dict) -> list:
    """
    Generate plain-register sentence variants for Japanese (ja.register_plain).

    ParseJpn's tabularLinearize gives both polite (Resp) and plain forms.
    The standard linearize() path always returns polite (ます/です).  This
    function surfaces the plain form so learners encounter both registers.

    Only V, V2, and A produce register contrasts.  N citation forms are the
    same in both registers.

    Returns sentence dicts with:
        "ja"   : plain-form surface string
        "label": "[plain] non-past" / "[plain] past" / "[plain] non-past negative" etc.
        "pattern": dict with ja_register="plain" for node-key mapping
        + polite-form linearizations of other languages (en/de/es) for context
    """
    ja = concretes.get("ja")
    if ja is None:
        return []

    if cat == "V":
        base_tree = f"UseV {fn}"
    elif cat == "V2":
        base_tree = f"SlashV2a {fn}"
    elif cat == "A":
        base_tree = f"PositA {fn}"
    else:
        return []

    try:
        expr = pgf.readExpr(base_tree)
        table = ja.tabularLinearize(expr)
    except Exception:
        return []

    other = {l: c for l, c in concretes.items() if l != "ja"}
    results = []

    for tense in ("TPres", "TPast"):
        for pol_gf, pol_ja in (("PPos", "Pos"), ("PNeg", "Neg")):
            # Look up the plain-form conjugation key
            if cat == "V":
                key = f"verb Me Anim Plain {tense} {pol_ja}"
            elif cat == "V2":
                key = f"s Me Plain {tense} {pol_ja}"
            else:  # A
                key = f"pred Plain {tense} {pol_ja}"

            plain = table.get(key, "")
            if not plain or _BRACKET_RE.search(plain):
                continue

            # Build a matching polite-form tree for companion language translations
            ta = f"(TTAnt {tense} ASimul)"
            if cat == "V":
                companion_tree = (
                    f"PhrUtt NoPConj (UttS (PredVPS (UsePron i_Pron) "
                    f"(MkVPS {ta} {pol_gf} (UseV {fn})))) NoVoc"
                )
            elif cat == "V2":
                companion_tree = (
                    f"PhrUtt NoPConj (UttS (PredVPS (UsePron i_Pron) "
                    f"(MkVPS {ta} {pol_gf} "
                    f"(ComplSlash (SlashV2a {fn}) (UsePron it_Pron))))) NoVoc"
                )
            else:  # A
                companion_tree = (
                    f"PhrUtt NoPConj (UttS (PredVPS (UsePron it_Pron) "
                    f"(MkVPS {ta} {pol_gf} "
                    f"(UseComp (CompAP (PositA {fn})))))) NoVoc"
                )

            lins = _lin_safe(other, companion_tree) or {}

            tense_label = "past" if tense == "TPast" else "non-past"
            neg_label   = " negative" if pol_gf == "PNeg" else ""
            label = f"[plain] {tense_label}{neg_label}"

            d = _compute_difficulty("UttS", tense, "ASimul", pol_gf, None, False)
            pattern = {
                "utt_type": "UttS", "tense": tense, "aspect": "ASimul",
                "polarity": pol_gf, "person": None, "verb_cat": "SlashV2a" if cat == "V2" else "UseV",
                "progressive": False, "attributive": False, "difficulty": d,
                "word_order": None, "voice": None,
                "ja_register": "plain",
            }

            results.append({"label": label, "tree": companion_tree,
                            "pattern": pattern, "ja": plain, **lins})

    return results


# ---------------------------------------------------------------------------
# Source sentence extraction
# ---------------------------------------------------------------------------

def _split_sentences(text: str, lang: str) -> list:
    """Split document text into sentences using spaCy."""
    try:
        nlp = _get_nlp(lang)
        doc = nlp(text)
        return [sent.text.strip() for sent in doc.sents
                if sent.text.strip() and len(sent.text.strip()) <= _MAX_EXAMPLE_LEN]
    except Exception:
        # Naive fallback
        return [s.strip() for s in re.split(r'(?<=[.!?])\s+', text)
                if s.strip() and len(s.strip()) <= _MAX_EXAMPLE_LEN]


def _find_source_sentences(word: str, sentences: list, lang: str,
                           max_n: int = _MAX_EXAMPLES) -> list:
    """
    Return up to max_n sentences containing `word` as a whole-word match.
    Shorter sentences are preferred (more useful as lesson examples).
    Japanese uses substring match since there are no word boundaries.
    """
    if not LANG_CONFIG.get(lang, {}).get("word_boundary_search", True):
        pattern = re.compile(re.escape(word))
    else:
        pattern = re.compile(r'\b' + re.escape(word) + r'\b', re.IGNORECASE)

    matches = [s for s in sentences if pattern.search(s)]
    matches.sort(key=len)
    return matches[:max_n]


# ---------------------------------------------------------------------------
# Entry assembly
# ---------------------------------------------------------------------------

def _get_concretes(grammar, source_lang: str, target_langs: list) -> dict:
    """
    Return {lang_code: pgf.Concr} for all requested languages.
    Grammar is Parse.pgf so concrete names are Parse{Suffix}.
    """
    concretes = {}
    for lang in set([source_lang] + target_langs):
        cfg = LANG_CONFIG.get(lang)
        if not cfg:
            continue
        name = f"Parse{cfg['gf_suffix']}"
        concrete = grammar.languages.get(name)
        if concrete:
            concretes[lang] = concrete
    return concretes


def _dispatch_generate(
    fn: str,
    gf_cat: str,
    concretes: dict,
    profile=None,           # SkillProfile | None
    source_patterns=None,   # Counter[GrammarPattern] | None
    target_lang: Optional[str] = None,
) -> list:
    """Select patterns from profile + source + node weakness, then generate sentences."""
    patterns = select_generation_patterns(
        gf_cat, profile, source_patterns or Counter(), target_lang=target_lang,
    )
    return generate_sentences(fn, gf_cat, concretes, patterns)


def _build_entry(
    word: str,
    gf_cat: str,
    fn: Optional[str],
    concretes: dict,
    source_lang: str,
    target_langs: list,
    source_sentences: list,
    grammar,
    alternates: Optional[list] = None,
    source_count: int = 0,
    profile=None,
    source_patterns=None,
    target_lang: Optional[str] = None,
) -> dict:
    entry = {
        "word": word,
        "gf_function": fn,
        "gf_cat": gf_cat,
        "in_wordnet": fn is not None,
        "translations": {},
        "sentences": [],
        "source_count": source_count,
        "alternates": alternates or [],
        "source_examples": [
            {"text": s, "translations": {}, "method": "source"}
            for s in source_sentences
        ],
    }

    if fn is None:
        return entry

    entry["translations"] = _bare_word(concretes, fn, gf_cat)
    entry["sentences"] = _dispatch_generate(
        fn, gf_cat, concretes, profile, source_patterns, target_lang,
    )

    return entry


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def quick_word_list(
    vocab: dict,
    source_lang: str,
    target_langs: list,
    pgf_path: str = "./Parse.pgf",
) -> list:
    """
    Fast vocabulary resolution without sentence generation.

    Runs the GF sense-ranking and translation lookup only — no sentence
    generation, no source pattern analysis, no NMT.  Typically completes
    in 5–15 seconds for a 50-word vocabulary.

    Used for the progressive-disclosure web flow: show users the word list
    immediately while the full build_lesson() call runs in the background.

    Returns the same schema as build_lesson() but with:
        sentences        = []   (filled by the background task)
        source_examples  = []   (filled by the background task)
        source_count     = 0    (filled by the background task)
    """
    grammar = _load_parse_grammar(pgf_path)
    concretes = _get_concretes(grammar, source_lang, target_langs)
    src_concrete = concretes.get(source_lang)
    src_lang = (_get_lang_for_concrete(src_concrete, grammar)
                if src_concrete else source_lang)

    entries = []
    for word, gf_cat in vocab.items():
        with _suppress_c_stdout():
            ranked_fns, boost = _rank_all_senses(
                word, gf_cat, src_concrete, [], grammar, concretes,
            )
        fn = _pick_primary(ranked_fns, gf_cat, concretes, word, src_lang)
        alternates = _build_alternates(gf_cat, fn, ranked_fns, boost, concretes, src_lang)
        translations = _bare_word(concretes, fn, gf_cat) if fn else {}
        entries.append({
            "word":          word,
            "gf_function":   fn,
            "gf_cat":        gf_cat,
            "in_wordnet":    fn is not None,
            "translations":  translations,
            "alternates":    alternates,
            "source_count":  0,
            "sentences":     [],
            "source_examples": [],
        })
    return entries


def build_lesson(
    vocab: dict,
    source_text: str,
    source_lang: str,
    target_langs: list,
    pgf_path: str = "./Parse.pgf",
    profile=None,        # SkillProfile | None — drives sentence pattern selection
    target_lang: Optional[str] = None,  # primary learning target for node scoring
) -> list:
    """
    Build lesson entries for every word in vocab.

    Parameters
    ----------
    vocab       : {word: gf_cat} — same format as extract_keywords output
    source_text : full raw text of the source document (not pre-chunked)
    source_lang : ISO language code of the source (e.g. "en", "es", "de", "ja")
    target_langs: list of ISO language codes to generate content for
    pgf_path    : path to Parse.pgf (default works when run from project root)

    Returns
    -------
    List of LessonEntry dicts. Each dict has:
        word          : str
        gf_function   : str | None
        gf_cat        : str ("N", "V", "V2", "A", "Adv")
        in_wordnet    : bool
        translations  : {lang: str}  — bare word translation via GF (primary sense)
        sentences     : [{"label": str, lang: str, ...}]  — generated examples
        source_count  : int  — times primary sense appeared in source parses (0 if
                               source parse skipped, e.g. German source)
        alternates    : [{"gf_function": str, "translations": {lang: str},
                          "source_count": int}]
                        Other senses with distinct target-language translations.
                        source_count > 0 means that sense appeared in source parses.
        source_examples: [{"text": str, "translations": {}, "method": "source"}]
    """
    grammar = _load_parse_grammar(pgf_path)
    concretes = _get_concretes(grammar, source_lang, target_langs)

    if source_lang not in concretes:
        raise ValueError(
            f"Parse{LANG_CONFIG[source_lang]['gf_suffix']} not in {pgf_path} — "
            f"recompile Parse.pgf with '{source_lang}' included"
        )

    src_concrete = concretes[source_lang]
    all_concretes = concretes  # includes source
    src_lang = _get_lang_for_concrete(src_concrete, grammar)  # may differ from source_lang if config mismatch

    # Pre-split document into sentences once (shared across all words)
    sentences = _split_sentences(source_text, source_lang)

    # Analyse source document grammar patterns once — used to prioritise sentence
    # structures that the learner will actually encounter in this document.
    from .pattern import patterns_in_source as _patterns_in_source
    source_patterns = _patterns_in_source(source_text, source_lang, grammar)

    entries = []
    for word, gf_cat in vocab.items():
        # Find source sentences containing this word
        source_sents = _find_source_sentences(word, sentences, source_lang)

        # Rank all senses once; reuse results for both primary selection
        # and alternate collection (avoids running lookupMorpho/parse twice).
        ranked_fns, boost = _rank_all_senses(
            word, gf_cat, src_concrete, source_sents, grammar, all_concretes,
        )

        fn = _pick_primary(ranked_fns, gf_cat, all_concretes, word, src_lang)

        alternates = _build_alternates(
            gf_cat, fn, ranked_fns, boost, all_concretes, src_lang,
        )

        entry = _build_entry(
            word, gf_cat, fn, all_concretes,
            source_lang, target_langs,
            source_sents, grammar,
            alternates=alternates,
            source_count=boost.get(fn, 0) if fn else 0,
            profile=profile,
            source_patterns=source_patterns,
            target_lang=target_lang or (target_langs[0] if target_langs else None),
        )
        entries.append(entry)

    return entries
