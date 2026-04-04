"""
Compound-word head extraction for morphological lookup.

Some languages (German in particular) form compounds productively, producing
words like "Elektroauto" or "Ladekabel" that don't appear in a general
dictionary even though their head components ("Auto", "Kabel") do.

compound_head() finds the shortest right-aligned component of a compound
that (a) matches the expected GF category and (b) is present in the grammar's
morphological index.  This allows build_grammar() and build_lesson() to
resolve domain-specific compound nouns to their WordNet head entries without
requiring an explicit compound dictionary.

Algorithm
---------
German compounds are head-final: the rightmost component determines the
category and core meaning.  We scan from the right, trying progressively
longer tails until a valid GF function is found.

Fugenelemente (linking morphemes: -s-, -es-, -en-, -e-, -er-, -ern-, -n-)
may appear at the split point.  We strip them from the left edge of each
candidate before falling through to the bare suffix, so:
    "Bundestag" + "s" + "wahl" → try "swahl", strip "s" → try "wahl" → found
    "Kinder"    + (none) + "wagen" → try "erwagen", try "wagen" → found

Minimum component length is 3 characters to avoid matching prepositions or
short grammatical words as spurious compound heads.

Usage
-----
Only called when LANG_CONFIG[lang]["compound_splitting"] is True.
"""

from contextlib import suppress
from typing import Optional


# GF category suffix sets — duplicated from generator.py to avoid a circular
# import (generator imports LANG_CONFIG; pipeline imports compound; compound
# must not import generator).
_CAT_SUFFIXES: dict = {
    "N":   ("_N",),
    "V":   ("_V",),
    "V2":  ("_V2",),
    "A":   ("_A",),
    "Adv": ("_Adv",),
}

# German Fugenelemente that may appear at the left edge of a compound suffix.
# Listed longest-first so we try longer morphemes before shorter ones.
_FUGEN = ("ens", "ern", "nen", "gen", "sen", "ten", "nen",
          "es", "en", "er", "ns", "s", "e", "n")

_MIN_LEN = 3


def compound_head(
    word: str,
    concrete,            # pgf.Concr — source-language concrete grammar
    gf_cat: str,
    lang_config: dict,
) -> Optional[str]:
    """
    Return the surface form of the compound's head component, or None.

    Parameters
    ----------
    word        : the surface form that failed a direct lookupMorpho()
    concrete    : the source-language GF concrete (already loaded)
    gf_cat      : expected GF category ("N", "V", "V2", "A", "Adv")
    lang_config : LANG_CONFIG entry for the source language

    Returns
    -------
    The surface form (correctly cased) of the head component if found in the
    morphological index with a matching category, else None.

    The caller is responsible for wrapping this in _suppress_c_stdout() if
    running inside a GF context that produces C-level stderr noise.
    """
    if not lang_config.get("compound_splitting"):
        return None

    lower = word.lower()
    n     = len(lower)

    # Scan right-to-left: start with the shortest possible tail (_MIN_LEN
    # chars) and grow until we exhaust the word.  The first match wins —
    # shortest match = rightmost atomic head.
    for start in range(n - _MIN_LEN, 1, -1):
        raw = lower[start:]
        if len(raw) < _MIN_LEN:
            continue

        candidates = _candidates(raw)

        for cand in candidates:
            # German nouns are capitalised — try both cases.
            for form in _both_cases(cand):
                with suppress(Exception):
                    if _any_cat_match(concrete.lookupMorpho(form), gf_cat):
                        return form

    return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _candidates(raw: str) -> list:
    """
    Build lookup candidates from a raw suffix by stripping Fugenelemente.

    Returns the raw suffix first (no stripping), then each variant with a
    leading Fugenelement removed.  Duplicates are suppressed.
    """
    seen   = set()
    result = []

    def _add(s):
        if s not in seen and len(s) >= _MIN_LEN:
            seen.add(s)
            result.append(s)

    _add(raw)
    for fugen in _FUGEN:
        if raw.startswith(fugen) and len(raw) - len(fugen) >= _MIN_LEN:
            _add(raw[len(fugen):])

    return result


def _both_cases(word: str):
    """Yield `word` and its title-cased variant (deduplicated)."""
    yield word
    titled = word[0].upper() + word[1:] if word else word
    if titled != word:
        yield titled


def _any_cat_match(morpho_iter, gf_cat: str) -> bool:
    """Return True if any (fn_name, tag, prob) entry matches gf_cat."""
    suffixes = _CAT_SUFFIXES.get(gf_cat, ())
    for fn_name, _tag, _prob in morpho_iter:
        if any(fn_name.endswith(s) for s in suffixes):
            return True
    return False
