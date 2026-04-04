"""
GF tree structural analysis for pedagogical grading.

GrammarPattern captures the structural properties of a GF-generated (or parsed)
sentence in a language-independent way.  It is used to:

  1. Annotate every sentence in build_lesson output with its grammatical
     complexity so the exercise selector can match sentences to user level.
  2. Analyse source documents to identify which structures the learner will
     encounter, so those structures can be prioritised in lesson generation.
  3. Group sentences across vocabulary items when building multiple-choice
     distractors (same difficulty + verb_cat = grammatically parallel option).
"""

import re
from collections import Counter
from dataclasses import dataclass
from typing import Optional

# ---------------------------------------------------------------------------
# Feature detectors — regex over GF abstract syntax tree strings.
# Tree strings look like:
#   PhrUtt NoPConj (UttS (PredVPS (UsePron i_Pron)
#     (MkVPS (TTAnt TPast ASimul) PNeg (UseV run_1_V)))) NoVoc
# All GF combinators are single words separated by spaces/parens, so \b
# word-boundary matching works reliably.
# ---------------------------------------------------------------------------

_TENSE_RE   = re.compile(r'\bTTAnt\s+(TPres|TPast|TFut|TCond)\s+(ASimul|AAnter)\b')
_POLARITY_RE = re.compile(r'\b(PPos|PNeg)\b')
_UTT_RE     = re.compile(r'\b(UttS|UttQS|UttNP|UttAdv)\b')
_VERB_RE    = re.compile(r'\b(UseV|SlashV2a|UseComp|ProgrVP)\b')
_PERSON_RE  = re.compile(r'\b(i_Pron|youSg_Pron|he_Pron|she_Pron|we_Pron|they_Pron|it_Pron)\b')
_ADJCN_RE   = re.compile(r'\bAdjCN\b')
_ADVS_RE   = re.compile(r'\bAdvS\b')
_COMPLS_RE = re.compile(r'\bComplVS\b')
_PASSV_RE  = re.compile(r'\bPassVPSlash\b')

# No language-specific constants here.
# Per-language behaviour is controlled by LANG_CONFIG flags:
#   slow_source_parse     — True means skip/replace GF parse() for source analysis
#   source_pattern_method — "gf" | "spacy_dep" | "none"

# ---------------------------------------------------------------------------
# GrammarPattern
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GrammarPattern:
    """
    Language-independent structural fingerprint of a GF sentence.
    Frozen so it can be used as a Counter key or in sets.

    Fields use the raw GF combinator names where unambiguous (tense, aspect,
    polarity, person) so comparisons between analyze_tree output and
    patterns_in_source output are exact.
    """
    utt_type:    str            # "UttS" | "UttQS" | "UttNP" | "UttAdv"
    tense:       Optional[str]  # "TPres" | "TPast" | "TFut" | "TCond" | None
    aspect:      Optional[str]  # "ASimul" | "AAnter" | None
    polarity:    Optional[str]  # "PPos" | "PNeg" | None
    person:      Optional[str]  # "i_Pron" | "youSg_Pron" | ... | None
    verb_cat:    Optional[str]  # "UseV" | "SlashV2a" | "UseComp" | None
    progressive: bool
    attributive: bool           # AdjCN — adjective used attributively
    difficulty:  int            # 1–5 (computed by _compute_difficulty)
    word_order:  Optional[str] = None  # "inv" | "v_end" | None
    voice:       Optional[str] = None  # "Pass" | "Pot" | "Caus" | None

    # ------------------------------------------------------------------
    # Human-readable helpers
    # ------------------------------------------------------------------

    @property
    def cefr_band(self) -> str:
        return {1: "A1", 2: "A2", 3: "B1", 4: "B2", 5: "C1"}.get(self.difficulty, "A1")

    @property
    def label(self) -> str:
        """Short human-readable description, e.g. 'past simple negative (V2, 1sg)'."""
        if self.utt_type == "UttNP":
            return "NP fragment"
        if self.utt_type == "UttAdv":
            return "adverb fragment"

        parts = []

        tense_labels = {
            "TPres": "present", "TPast": "past",
            "TFut": "future",   "TCond": "conditional",
        }
        aspect_labels = {"ASimul": "simple", "AAnter": "perfect"}
        tense_str = tense_labels.get(self.tense or "", "")
        aspect_str = aspect_labels.get(self.aspect or "", "")

        if self.progressive:
            parts.append(f"{tense_str} progressive" if tense_str else "progressive")
        elif tense_str and aspect_str:
            parts.append(f"{tense_str} {aspect_str}")
        elif tense_str:
            parts.append(tense_str)

        if self.polarity == "PNeg":
            parts.append("negative")

        if self.utt_type == "UttQS":
            parts.append("question")

        if self.word_order == "inv":
            parts.append("(V-S inverted)")
        elif self.word_order == "v_end":
            parts.append("(verb-final clause)")
        if self.voice == "Pass":
            parts.append("passive")
        elif self.voice == "Pot":
            parts.append("potential")
        elif self.voice == "Caus":
            parts.append("causative")

        extras = []
        if self.verb_cat:
            extras.append(self.verb_cat)
        if self.person:
            extras.append(self.person)
        if extras:
            parts.append(f"({', '.join(extras)})")

        return " ".join(parts) if parts else "sentence"


# ---------------------------------------------------------------------------
# Difficulty scoring
# ---------------------------------------------------------------------------

def _compute_difficulty(
    utt_type: str,
    tense: Optional[str],
    aspect: Optional[str],
    polarity: Optional[str],
    person: Optional[str],
    progressive: bool,
    word_order: Optional[str] = None,
    voice: Optional[str] = None,
) -> int:
    """
    Map structural features to a 1–5 difficulty scale:
        1  A1  NP/Adv fragments; copula "it is [adj]"
        2  A2  Present/past simple (default persons: I/you/it)
        3  B1  Future, negation, progressive, non-default persons
        4  B2  Conditional, any perfect aspect
        5  C1  Combinations of the above
    """
    if utt_type in ("UttNP", "UttAdv"):
        return 1

    # Base from tense + aspect
    base = 2
    if aspect == "AAnter":            # any perfect aspect
        base = 4
    elif tense == "TCond":
        base = 4
    elif tense == "TFut":
        base = 3
    # TPres/TPast ASimul → 2

    modifiers = 0

    if polarity == "PNeg":
        modifiers += 1

    if progressive:
        modifiers += 1

    # Non-default persons require knowing gender-specific / plural conjugation
    _default_persons = {None, "i_Pron", "it_Pron", "youSg_Pron"}
    if person not in _default_persons:
        modifiers += 1

    if utt_type == "UttQS":
        modifiers += 1

    if word_order == "inv":
        modifiers += 1
    elif word_order == "v_end":
        modifiers += 2

    if voice in ("Pass", "Pot"):
        modifiers += 1
    elif voice == "Caus":
        modifiers += 2

    return max(1, min(5, base + modifiers))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze_tree(tree_str: str) -> GrammarPattern:
    """
    Extract a GrammarPattern from a GF abstract syntax tree string.

    Works on both programmatically generated trees (from generator.py)
    and parse trees produced by pgf's concrete.parse() converted to str().
    """
    # Utterance type (first match wins — UttQS appears before UttS in tree)
    utt_m   = _UTT_RE.search(tree_str)
    tense_m = _TENSE_RE.search(tree_str)
    pol_m   = _POLARITY_RE.search(tree_str)
    pers_m  = _PERSON_RE.search(tree_str)

    utt_type = utt_m.group(1)   if utt_m   else "UttS"
    tense    = tense_m.group(1) if tense_m else None
    aspect   = tense_m.group(2) if tense_m else None
    polarity = pol_m.group(1)   if pol_m   else None
    person   = pers_m.group(1)  if pers_m  else None

    # Collect all verb-related nodes; ProgrVP wraps the actual verb node
    verb_hits = [m.group(1) for m in _VERB_RE.finditer(tree_str)]
    progressive = "ProgrVP" in verb_hits
    verb_cat    = next((v for v in verb_hits if v != "ProgrVP"), None)

    attributive = bool(_ADJCN_RE.search(tree_str))

    word_order = None
    if _ADVS_RE.search(tree_str):
        word_order = "inv"
    elif _COMPLS_RE.search(tree_str):
        word_order = "v_end"

    voice = None
    if _PASSV_RE.search(tree_str):
        voice = "Pass"

    difficulty = _compute_difficulty(utt_type, tense, aspect, polarity,
                                     person, progressive, word_order, voice)

    return GrammarPattern(
        utt_type=utt_type,
        tense=tense,
        aspect=aspect,
        polarity=polarity,
        person=person,
        verb_cat=verb_cat,
        progressive=progressive,
        attributive=attributive,
        difficulty=difficulty,
        word_order=word_order,
        voice=voice,
    )


def german_pt_patterns(text: str) -> dict:
    """
    Lightweight detection of German Processability Theory word-order phenomena
    in raw text — does NOT require a GF parse.

    Returns a dict of detected PT phenomena and their occurrence counts:
        {
          "wo_sep":   int,  # separable verb prefix at clause end
          "wo_inv":   int,  # V–S inversion after fronted element
          "wo_v_end": int,  # verb-final in subordinate clause
        }

    This is used during source-document analysis for German to estimate which
    PT stages are present in the input, so that generated exercises can be
    scoped to structures the learner is likely to encounter.

    German source analysis is skipped in patterns_in_source() because parsing
    is too slow (~15s/sentence), but this regex-based function is fast.
    """
    from .nodes import _DE_SEP_PREFIXES, _DE_SUB_CONJ, _DE_INV_RE

    counts = {"wo_sep": 0, "wo_inv": 0, "wo_v_end": 0}

    for sentence in re.split(r'(?<=[.!?])\s+', text):
        sentence = sentence.strip()
        if not sentence:
            continue

        # Separable prefix at sentence end
        last_word = sentence.rstrip(",.!?").rsplit()[-1].lower() if sentence.split() else ""
        if last_word in _DE_SEP_PREFIXES:
            counts["wo_sep"] += 1

        # Inversion after fronted element
        if _DE_INV_RE.search(sentence):
            counts["wo_inv"] += 1

        # Subordinate clause (triggers verb-final)
        if _DE_SUB_CONJ.search(sentence):
            counts["wo_v_end"] += 1

    return counts


def patterns_in_source(
    text: str,
    lang: str,
    grammar,
    max_sents: int = 30,
) -> "Counter[GrammarPattern]":
    """
    Extract GrammarPatterns from a sample of source-text sentences.

    Dispatches to the method specified by LANG_CONFIG[lang]["source_pattern_method"]:
        "gf"       — parse with GF's chart parser (accurate; slow for German)
        "spacy_dep"— extract patterns via spaCy dependency parse (fast; approximate)
        "none"     — return empty Counter (used when no reliable method exists)

    Returns Counter{GrammarPattern: count} used by select_generation_patterns()
    to prioritise sentence structures the learner will encounter in the document.
    """
    from .config import LANG_CONFIG

    cfg = LANG_CONFIG.get(lang, {})
    method = cfg.get("source_pattern_method", "gf")

    if method == "none" or cfg.get("slow_source_parse", False) and method == "gf":
        return Counter()

    if method == "spacy_dep":
        return _spacy_dep_patterns(text, lang, max_sents)

    # method == "gf"
    from .pipeline import _suppress_c_stdout

    concrete = grammar.languages.get(f"Parse{cfg.get('gf_suffix', '')}")
    if concrete is None:
        return Counter()

    from .generator import _split_sentences
    sentences = [s for s in _split_sentences(text, lang) if len(s) <= 100][:max_sents]

    result: Counter = Counter()
    for sent in sentences:
        try:
            with _suppress_c_stdout():
                it = concrete.parse(sent)
                _prob, expr = next(it)
                del it
            result[analyze_tree(str(expr))] += 1
        except Exception:
            pass

    return result


def _spacy_dep_patterns(
    text: str,
    lang: str,
    max_sents: int = 30,
) -> "Counter[GrammarPattern]":
    """
    Extract GrammarPatterns via spaCy dependency parse.

    Currently implements German (TIGER dep scheme, STTS morphology tags).
    For other languages with source_pattern_method="spacy_dep" that lack a
    mapping implementation, returns an empty Counter gracefully.

    The spaCy model is already loaded by extract_keywords(), so there is no
    additional load-time cost.
    """
    from .keywords import _get_nlp

    result: Counter = Counter()

    _mapper = _SPACY_DEP_MAPPERS.get(lang)
    if _mapper is None:
        return result

    try:
        nlp = _get_nlp(lang)
    except Exception:
        return result

    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text)
                 if s.strip() and len(s.strip()) <= 100][:max_sents]

    for sent_text in sentences:
        try:
            doc = nlp(sent_text)
            pat = _mapper(doc)
            if pat is not None:
                result[pat] += 1
        except Exception:
            pass

    return result


def _map_german_doc(doc) -> Optional[GrammarPattern]:
    """
    Map a spaCy-parsed German sentence to a GrammarPattern.

    Uses TIGER dependency scheme and STTS morphological features as provided
    by de_core_news_sm and de_core_news_md/lg.  Features that are absent from
    the small model (e.g. some morphological fields) are handled gracefully
    by defaulting to the simplest/most common value.
    """
    # Find the root finite verb
    root = next((t for t in doc if t.dep_ == "ROOT"), None)
    if root is None or root.pos_ not in ("VERB", "AUX"):
        return None

    morph = root.morph

    # --- Tense / aspect ---
    tense: Optional[str] = None
    aspect = "ASimul"

    mood_list  = morph.get("Mood")
    tense_list = morph.get("Tense")

    if mood_list and "Sub" in mood_list:
        tense = "TCond"   # Konjunktiv II maps to GF conditional
    elif tense_list:
        tense = "TPast" if "Past" in tense_list else "TPres"

    # Perfekt: haben/sein auxiliary + Partizip II
    aux_toks = [t for t in doc if t.dep_ in ("aux", "auxpass")]
    has_haben_sein = any(t.lemma_ in ("haben", "sein") for t in aux_toks)
    has_partizip   = any(
        "Part" in t.morph.get("VerbForm") and t.pos_ == "VERB"
        for t in doc
        if t.morph.get("VerbForm")
    )
    if has_haben_sein and has_partizip:
        aspect = "AAnter"

    # Futur I: werden + infinitive
    if any(t.lemma_ == "werden" and t.dep_ == "aux" for t in doc):
        tense  = "TFut"
        aspect = "ASimul"

    # --- Polarity ---
    polarity = (
        "PNeg"
        if any(t.dep_ == "ng" or t.lower_ in ("nicht", "kein", "keine", "keinen", "keinem")
               for t in doc)
        else "PPos"
    )

    # --- Utterance type ---
    utt_type = "UttQS" if doc.text.strip().endswith("?") else "UttS"

    # --- Person (from morphology of the subject) ---
    person: Optional[str] = None
    subj = next((t for t in doc if t.dep_ in ("sb", "nsubj")), None)
    if subj:
        sm = subj.morph
        pers_list = sm.get("Person")
        num_list  = sm.get("Number")
        if pers_list and num_list:
            p, n = pers_list[0], num_list[0]
            person = {
                ("1", "Sing"): "i_Pron",
                ("2", "Sing"): "youSg_Pron",
                ("3", "Sing"): "he_Pron",
                ("1", "Plur"): "we_Pron",
                ("3", "Plur"): "they_Pron",
            }.get((p, n))

    # --- Verb category ---
    verb_cat = "SlashV2a" if any(t.dep_ in ("oa", "obj") for t in doc) else "UseV"

    # --- Attributive adjective ---
    attributive = any(t.dep_ == "nk" and t.pos_ == "ADJ" for t in doc)

    # --- Word order (German-specific) ---
    # Detect inversion (fronted adverb/element triggers V-S order) and
    # verb-final (subordinating conjunction triggers clause-final verb).
    # Both detections use the same regex patterns as german_pt_patterns().
    from .nodes import _DE_INV_RE, _DE_SUB_CONJ
    word_order = None
    if _DE_SUB_CONJ.search(doc.text):
        word_order = "v_end"    # subordinate clause — harder, takes priority
    elif _DE_INV_RE.search(doc.text):
        word_order = "inv"

    difficulty = _compute_difficulty(utt_type, tense, aspect, polarity, person, False,
                                     word_order=word_order)

    return GrammarPattern(
        utt_type=utt_type, tense=tense, aspect=aspect, polarity=polarity,
        person=person, verb_cat=verb_cat, progressive=False,
        attributive=attributive, difficulty=difficulty,
        word_order=word_order, voice=None,
    )


def _map_japanese_doc(doc) -> Optional[GrammarPattern]:
    """
    Map a spaCy-parsed Japanese sentence to a GrammarPattern.

    Uses GiNZA (SudachiPy tokenizer) with Universal Dependencies.
    GiNZA stores morphological information in the Inflection feature rather
    than UD Tense/Mood, so detection relies on auxiliary lemmas:
      - Past:        AUX token with lemma="た"
      - Conditional: AUX with inflection containing "仮定形"
      - Negative:    AUX with lemma="ない" or "ん"
      - Progressive: SCONJ te-marker (lemma="て") + VERB/AUX with lemma="いる"

    Person is not detected — Japanese lacks grammatical person marking.
    """
    root = next((t for t in doc if t.dep_ == "ROOT"), None)
    if root is None:
        return None

    text = doc.text.strip()

    # --- Utterance type ---
    # Question marker か may be a final particle or part of か？
    utt_type = "UttQS" if any(text.endswith(q) for q in ("か", "か。", "か?", "？", "?")) else "UttS"

    # --- Tense ---
    # GiNZA: past tense is signalled by AUX lemma "た" (written た/だ after /n/).
    # Conditional: ば or たら as SCONJ marker; also catch 仮定形 anywhere in
    # the Inflection feature string (e.g. '五段-カ行;仮定形-一般').
    has_past = any(t.lemma_ == "た" and t.pos_ == "AUX" for t in doc)
    has_cond = any(t.lemma_ in ("ば", "たら") and t.pos_ == "SCONJ" for t in doc) or any(
        any("仮定形" in v for v in (t.morph.get("Inflection") or []))
        for t in doc
    )
    if has_cond:
        tense: Optional[str] = "TCond"
    elif has_past:
        tense = "TPast"
    else:
        tense = "TPres"

    # --- Polarity ---
    # Negative auxiliaries in GiNZA: ない (plain), ん (contracted), ません (polite).
    # ません is tokenised as ます+ん or ません; check both lemmas.
    _NEG_LEMMAS = frozenset({"ない", "ん", "ぬ", "ず"})
    polarity = (
        "PNeg"
        if any(t.lemma_ in _NEG_LEMMAS and t.pos_ == "AUX" for t in doc)
        else "PPos"
    )

    # --- Progressive (ている / でいる construction) ---
    # GiNZA tokenises: 走っ(VERB) + て(SCONJ, dep=mark, lemma=て) +
    #                  い(VERB, dep=fixed, lemma=いる) + ます(AUX)
    # Detection: て as SCONJ/mark AND lemma=いる/ある/おる anywhere in doc.
    _IRU_LEMMAS = frozenset({"いる", "ある", "おる"})
    has_te_mark = any(t.lemma_ == "て" and t.pos_ in ("SCONJ", "AUX") for t in doc)
    has_iru     = any(t.lemma_ in _IRU_LEMMAS for t in doc)
    progressive = has_te_mark and has_iru

    # --- Verb category: を object particle → transitive ---
    has_wo = any(t.text == "を" and t.dep_ == "case" for t in doc)
    verb_cat = "SlashV2a" if has_wo else "UseV"

    # --- Attributive adjective ---
    attributive = any(t.dep_ == "amod" and t.pos_ == "ADJ" for t in doc)

    aspect = "ASimul"
    person = None

    # --- Voice (Japanese-specific) ---
    # Passive: GiNZA tags the passive auxiliary られる/れる as AUX tokens.
    _PASS_LEMMAS = frozenset({"られる", "れる"})
    voice = None
    if any(t.lemma_ in _PASS_LEMMAS and t.pos_ == "AUX" for t in doc):
        voice = "Pass"

    difficulty = _compute_difficulty(utt_type, tense, aspect, polarity, person, progressive,
                                     voice=voice)

    return GrammarPattern(
        utt_type=utt_type, tense=tense, aspect=aspect, polarity=polarity,
        person=person, verb_cat=verb_cat, progressive=progressive,
        attributive=attributive, difficulty=difficulty,
        word_order=None, voice=voice,
    )


# Registry: lang_code → doc mapper function.
# Add a new entry here (and implement the mapper) to support a new language
# in _spacy_dep_patterns().
_SPACY_DEP_MAPPERS = {
    "de": _map_german_doc,
    "ja": _map_japanese_doc,
}
