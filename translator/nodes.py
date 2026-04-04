"""
Per-language grammar skill node taxonomy and key extraction.

Node keys follow the convention:
  Universal:          "tense.TPast", "aspect.AAnter", "polarity.PNeg", ...
  Language-specific:  "es.copula", "de.konjunktiv2", "ja.particle_wa_ga", ...

Each node represents a single morpho-syntactic phenomenon.  Compound feature
combinations (e.g. "tense.TPast+polarity.PNeg") are intentionally NOT tracked
— data sparsity makes per-cell mastery estimates unreliable with typical usage
volumes.

Nodes fall into two tiers:

  Tier 1 — derivable from GrammarPattern (populated automatically on every
            exercise attempt via pattern_to_node_keys()).

  Tier 2 — require surface-form analysis beyond GrammarPattern (German word
            order stages, Japanese particles, Spanish ser/estar distinction).
            These nodes appear in the taxonomy but are populated separately by
            the services layer when the richer sentence data is available.
            Tier-2 nodes are marked in the catalogs below.
"""

import re
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Node key catalogs
# Used for display labels and to enumerate valid node keys per language.
# ---------------------------------------------------------------------------

UNIVERSAL_NODES: Dict[str, str] = {
    "tense.TPres":        "Present tense",
    "tense.TPast":        "Past tense",
    "tense.TFut":         "Future tense",
    "tense.TCond":        "Conditional tense",
    "aspect.AAnter":      "Perfect aspect",
    "polarity.PNeg":      "Negation",
    "struct.question":    "Question form",
    "struct.progressive": "Progressive aspect",
    "struct.NP_fragment": "Noun-phrase fragment",
    "person.3sg":         "Third-person singular (agreement morphology)",
    "person.1pl":         "First-person plural",
    "person.plural":      "Third-person plural / second-person plural",
}

SPANISH_NODES: Dict[str, str] = {
    # Tier 1 — derivable from GrammarPattern
    "es.copula":           "Copula verb (ser / estar context)",
    "es.gender_agreement": "Noun–adjective gender agreement",
    # Tier 2 — require lexical aspect class annotation on the GF function
    "es.pret_achievement": "Preterite: achievement / punctual verbs",
    "es.pret_state":       "Preterite: state verbs (ser, estar, tener…)",
    "es.impf_state":       "Imperfect: state / habitual meaning",
    "es.impf_activity":    "Imperfect: activity verbs",
    # Tier 2 — require mood analysis beyond current GrammarPattern
    "es.subj_nominal":     "Subjunctive in nominal clauses (quiero que…)",
    "es.subj_adverbial":   "Subjunctive in adverbial clauses (para que…)",
    # Tier 2 — require surface ser/estar disambiguation
    "es.ser_estar":        "Ser vs. estar contrast",
    # Tier 2 — require clitic detection in linearization
    "es.clitic_do":        "Direct-object clitic pronouns (lo / la / los / las)",
    "es.clitic_io":        "Indirect-object clitic pronouns (le / les)",
}

GERMAN_NODES: Dict[str, str] = {
    # Tier 1 — derivable from GrammarPattern
    "de.konjunktiv2":    "Konjunktiv II (hätte / wäre / würde + inf)",
    "de.partizip2":      "Past participle (Partizip II) in Perfekt",
    # Tier 2 — require word-order analysis of linearized German output
    "de.wo_sep":         "Separable verb — prefix separation (PT Stage 3)",
    "de.wo_inv":         "Subject–verb inversion after fronting (PT Stage 4)",
    "de.wo_v_end":       "Verb-final in subordinate clauses (PT Stage 5)",
    # Tier 2 — require case / gender analysis of linearized German output
    "de.case_acc":       "Accusative case on full noun phrases",
    "de.case_dat":       "Dative case",
    "de.case_gen":       "Genitive case",
    "de.article_gender": "Grammatical gender on articles (der / die / das)",
}

JAPANESE_NODES: Dict[str, str] = {
    # Tier 1 — partially derivable from GrammarPattern
    "ja.te_iru_prog":       "て-いる: progressive meaning (activity verbs)",
    "ja.register_polite":   "Polite register (ます / です)",
    # Tier 2 — require surface particle / morphology analysis
    "ja.te_iru_result":     "て-いる: resultative / state meaning",
    "ja.particle_wo":       "Object particle を",
    "ja.particle_ni_dir":   "Directional particle に",
    "ja.particle_ni_loc":   "Locative particle に (existence site)",
    "ja.particle_de_loc":   "Locative particle で (action site)",
    "ja.particle_ni_de":    "に vs. で location distinction",
    "ja.particle_wa_ga":    "Topic は vs. subject が contrast",
    "ja.potential":         "Potential form (~られる / ~える)",
    "ja.passive":           "Passive form (~られる / ~される)",
    "ja.causative":         "Causative form (~させる / ~せる)",
    "ja.causative_passive": "Causative-passive (~させられる)",
    "ja.register_plain":    "Plain / casual register",
}

ALL_NODES: Dict[str, str] = {
    **UNIVERSAL_NODES,
    **SPANISH_NODES,
    **GERMAN_NODES,
    **JAPANESE_NODES,
}

# Per-language node catalogs (universal nodes are always applicable)
LANG_NODES: Dict[str, Dict[str, str]] = {
    "es": SPANISH_NODES,
    "de": GERMAN_NODES,
    "ja": JAPANESE_NODES,
}

# ---------------------------------------------------------------------------
# Person classification helpers
# ---------------------------------------------------------------------------

_3SG_PERSONS    = frozenset({"he_Pron", "she_Pron"})
_1PL_PERSONS    = frozenset({"we_Pron"})
_PLURAL_PERSONS = frozenset({"they_Pron", "youPl_Pron"})
_DEFAULT_PERSONS = frozenset({None, "i_Pron", "youSg_Pron", "it_Pron"})

# ---------------------------------------------------------------------------
# Key extraction
# ---------------------------------------------------------------------------


def _get(obj: Any, field: str, default: Any = None) -> Any:
    """Attribute or dict access — accepts both GrammarPattern and plain dicts."""
    if isinstance(obj, dict):
        return obj.get(field, default)
    return getattr(obj, field, default)


def pattern_to_node_keys(pattern: Any, target_lang: str) -> List[str]:
    """
    Extract the grammar skill node keys exercised by a GrammarPattern.

    Accepts either a GrammarPattern instance or a plain dict with the same
    fields (as stored in ExerciseAttempt.pattern and GeneratedSentence.pattern).

    Returns only nodes meaningfully tested by this pattern — features that
    require specific grammatical knowledge to answer correctly.  Default /
    baseline features (present simple, 1sg, positive polarity) produce no node
    key unless the feature itself is the focus (e.g. "tense.TPres" is emitted
    for completeness at A1 but is not boosted in scoring).

    Language-specific Tier-1 keys are appended where derivable from the
    abstract GrammarPattern.  Tier-2 keys must be injected separately.
    """
    tense       = _get(pattern, "tense")
    aspect      = _get(pattern, "aspect")
    polarity    = _get(pattern, "polarity")
    utt_type    = _get(pattern, "utt_type", "UttS")
    person      = _get(pattern, "person")
    progressive = _get(pattern, "progressive", False)
    attributive = _get(pattern, "attributive", False)
    verb_cat    = _get(pattern, "verb_cat")

    keys: List[str] = []

    # --- Universal keys ---

    # Tense (emit all tenses; present is the A1/default baseline)
    if tense:
        keys.append(f"tense.{tense}")

    # Perfect aspect
    if aspect == "AAnter":
        keys.append("aspect.AAnter")

    # Negation
    if polarity == "PNeg":
        keys.append("polarity.PNeg")

    # Question form
    if utt_type == "UttQS":
        keys.append("struct.question")

    # NP fragment
    if utt_type == "UttNP":
        keys.append("struct.NP_fragment")

    # Progressive
    if progressive:
        keys.append("struct.progressive")

    # Non-default persons (trigger agreement morphology)
    if person in _3SG_PERSONS:
        keys.append("person.3sg")
    elif person in _1PL_PERSONS:
        keys.append("person.1pl")
    elif person in _PLURAL_PERSONS:
        keys.append("person.plural")

    # --- Language-specific Tier-1 keys ---

    if target_lang == "es":
        if verb_cat == "UseComp":
            keys.append("es.copula")
        if attributive:
            keys.append("es.gender_agreement")

    elif target_lang == "de":
        # GF represents Konjunktiv II as TCond
        if tense == "TCond":
            keys.append("de.konjunktiv2")
        # Partizip II appears in Perfekt (AAnter)
        if aspect == "AAnter":
            keys.append("de.partizip2")

    elif target_lang == "ja":
        ja_register = _get(pattern, "ja_register")
        if ja_register == "plain":
            keys.append("ja.register_plain")
        else:
            keys.append("ja.register_polite")
        # Progressive meaning of て-いる
        if progressive:
            keys.append("ja.te_iru_prog")

    # --- Word order and voice (from pattern structural fields) ---
    word_order = _get(pattern, "word_order")
    voice      = _get(pattern, "voice")

    if word_order == "inv":
        keys.append("de.wo_inv")
    elif word_order == "v_end":
        keys.append("de.wo_v_end")

    if voice == "Pass":
        keys.append("ja.passive")
    elif voice == "Pot":
        keys.append("ja.potential")
    elif voice == "Caus":
        keys.append("ja.causative")

    return list(dict.fromkeys(keys))  # deduplicate, preserve order


# ---------------------------------------------------------------------------
# Tier-2 surface analysis helpers
# ---------------------------------------------------------------------------

# German separable prefixes (finite verb sends prefix to clause-final position)
_DE_SEP_PREFIXES = frozenset({
    "ab", "an", "auf", "aus", "bei", "ein", "fest", "her", "hin",
    "los", "mit", "nach", "nieder", "vor", "weg", "zu", "zurück",
    "zusammen", "weiter", "raus", "rein", "ran",
})

# German subordinating conjunctions that trigger verb-final order
_DE_SUB_CONJ = re.compile(
    r'\b(weil|dass|obwohl|wenn|als|damit|ob|während|nachdem|bevor|'
    r'seit|seitdem|falls|sodass|bis|ehe|sofern|sobald)\b',
    re.IGNORECASE,
)

# German inversion trigger: sentence starts with non-subject adverb/time expression
# followed by V–S order (finite verb comes before personal pronoun)
_DE_INV_RE = re.compile(
    r'^(Heute|Gestern|Morgen|Dann|Dort|Hier|Jetzt|Trotzdem|Deshalb|Daher|'
    r'Danach|Davor|Dazu|Also|Leider|Natürlich|Vielleicht|Normalerweise|'
    r'Manchmal|Oft|Immer|Nie|Selten)\s+\w+\s+(ich|er|sie|es|wir|ihr)\b',
    re.IGNORECASE,
)

# Japanese particle patterns
_JA_WO   = re.compile(r'を')
_JA_NI   = re.compile(r'に')
_JA_DE   = re.compile(r'で')
_JA_WA   = re.compile(r'は')
_JA_GA   = re.compile(r'が')
_JA_IMAS = re.compile(r'(います|あります|いる|ある)')  # existence / locative

# Spanish copula detection
_ES_SER   = re.compile(r'\b(soy|eres|es|somos|sois|son|era|eras|éramos|eran|fui|fue|fueron)\b', re.IGNORECASE)
_ES_ESTAR = re.compile(r'\b(estoy|estás|está|estamos|estáis|están|estaba|estabas|estábamos|estaban|estuve|estuvo|estuvieron)\b', re.IGNORECASE)

# Spanish object clitics
_ES_CLITIC_DO = re.compile(r'\b(lo|la|los|las)\s+\w', re.IGNORECASE)
_ES_CLITIC_IO = re.compile(r'\b(le|les)\s+\w', re.IGNORECASE)


def surface_node_keys(sentence_dict: dict, target_lang: str) -> List[str]:
    """
    Extract Tier-2 grammar skill node keys by analysing the linearized target text.

    sentence_dict : a GeneratedSentence-style dict, or any dict containing the
                    target-language linearization under the language-code key.
    target_lang   : ISO code of the language being analysed.

    Returns a list of node keys (possibly empty) for nodes derivable only from
    surface text analysis — things not capturable from the GrammarPattern alone.

    Call this *in addition to* pattern_to_node_keys() to get the full picture.
    Tier-1 keys are not re-emitted here; callers should union the two lists.
    """
    text = sentence_dict.get(target_lang, "")
    if not text:
        return []

    keys: List[str] = []

    if target_lang == "de":
        words = text.split()
        # --- wo_sep: separable prefix at clause end ---
        # Heuristic: last content word is a known separable prefix
        if words and words[-1].lower().rstrip(",.!?") in _DE_SEP_PREFIXES:
            keys.append("de.wo_sep")

        # --- wo_inv: V–S inversion after fronted adverb ---
        if _DE_INV_RE.search(text):
            keys.append("de.wo_inv")

        # --- wo_v_end: subordinate clause with verb-final order ---
        if _DE_SUB_CONJ.search(text):
            keys.append("de.wo_v_end")

        # --- article_gender: any definite article present (der/die/das/den/dem/des) ---
        if re.search(r'\b(der|die|das|den|dem|des|ein|eine|einen|einem|einer|eines)\b',
                     text, re.IGNORECASE):
            keys.append("de.article_gender")

        # --- case detection (accusative / dative / genitive markers) ---
        if re.search(r'\b(den|einen|ihn|keinen)\b', text, re.IGNORECASE):
            keys.append("de.case_acc")
        if re.search(r'\b(dem|einem|ihm|ihr|ihnen|uns|euch)\b', text, re.IGNORECASE):
            keys.append("de.case_dat")
        # Genitive: des/eines (masc./neut.) and possessive -es/-er endings
        # Avoids 'der' (ambiguous nom./gen.) and 'die' (ambiguous).
        if re.search(
            r'\b(des|eines|keines|meines|deines|seines|ihres|unseres|eures|deren|dessen)\b',
            text, re.IGNORECASE
        ):
            keys.append("de.case_gen")

    elif target_lang == "ja":
        if _JA_WO.search(text):
            keys.append("ja.particle_wo")
        if _JA_NI.search(text):
            # Distinguish locative に (with ある/いる) vs directional に
            if _JA_IMAS.search(text):
                keys.append("ja.particle_ni_loc")
            else:
                keys.append("ja.particle_ni_dir")
        if _JA_DE.search(text):
            keys.append("ja.particle_de_loc")
        if _JA_WA.search(text) and _JA_GA.search(text):
            keys.append("ja.particle_wa_ga")

    elif target_lang == "es":
        has_ser   = bool(_ES_SER.search(text))
        has_estar = bool(_ES_ESTAR.search(text))
        if has_ser and has_estar:
            keys.append("es.ser_estar")
        if _ES_CLITIC_DO.search(text):
            keys.append("es.clitic_do")
        if _ES_CLITIC_IO.search(text):
            keys.append("es.clitic_io")

    return list(dict.fromkeys(keys))  # deduplicate, preserve order


def node_weakness_score(pattern: Any, profile: Any, target_lang: str) -> float:
    """
    Score how much this pattern's nodes need practice, based on the skill profile.

    Returns a float ≥ 0.  Higher = more practice needed.
    Used to rank patterns within a difficulty bucket in select_generation_patterns().
    """
    if profile is None:
        return 0.0
    keys = pattern_to_node_keys(pattern, target_lang)
    score = 0.0
    for key in keys:
        acc = profile.node_accuracy(key, mode="r")
        if acc is None:
            score += 1.0          # unseen node — worth practicing
        elif acc < MASTERY_THRESHOLD:
            score += (MASTERY_THRESHOLD - acc) * 3.0   # struggling — boost
    return score


# Mastery threshold used in node_weakness_score (mirrors skill.MASTERY_THRESHOLD)
MASTERY_THRESHOLD = 0.80
