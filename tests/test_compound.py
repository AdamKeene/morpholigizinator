"""
Unit tests for translator/compound.py.

No GF grammar required — uses a mock concrete that simulates lookupMorpho.
"""
import pytest
from unittest.mock import MagicMock
from translator.compound import compound_head, _candidates, _both_cases


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_concrete(known: set):
    """
    Return a mock pgf.Concr whose lookupMorpho(word) returns a fake hit
    iff word.lower() is in `known`, with a function name ending in _N.
    """
    def _lookup(w):
        if w.lower() in known:
            return [(f"{w.lower()}_1_N", "Sg Nom", 1.0)]
        return []

    m = MagicMock()
    m.lookupMorpho.side_effect = _lookup
    return m


_DE_CFG = {"compound_splitting": True}
_NO_CFG = {"compound_splitting": False}


# ---------------------------------------------------------------------------
# _candidates
# ---------------------------------------------------------------------------

class TestCandidates:
    def test_raw_always_included(self):
        assert "auto" in _candidates("auto")

    def test_fugen_s_stripped(self):
        # "swahl" → strip leading "s" → "wahl"
        cands = _candidates("swahl")
        assert "wahl" in cands

    def test_fugen_en_stripped(self):
        cands = _candidates("enkind")
        # "en" + "kind" — strip "en" → "kind"
        assert "kind" in cands

    def test_no_stripping_when_too_short(self):
        # "sab" is only 3 chars after stripping "s" → "ab" (< MIN_LEN=3) should NOT appear
        cands = _candidates("sab")
        assert "ab" not in cands

    def test_no_duplicate_raw(self):
        cands = _candidates("wagen")
        assert cands.count("wagen") == 1


# ---------------------------------------------------------------------------
# _both_cases
# ---------------------------------------------------------------------------

class TestBothCases:
    def test_yields_lower_and_titled(self):
        assert list(_both_cases("auto")) == ["auto", "Auto"]

    def test_no_duplicate_if_already_titled(self):
        assert list(_both_cases("Auto")) == ["Auto"]

    def test_single_char(self):
        result = list(_both_cases("a"))
        assert "a" in result


# ---------------------------------------------------------------------------
# compound_head
# ---------------------------------------------------------------------------

class TestCompoundHead:
    def test_simple_compound_resolved(self):
        # "Elektroauto" → head should be "auto" / "Auto"
        concrete = _mock_concrete({"auto"})
        result = compound_head("Elektroauto", concrete, "N", _DE_CFG)
        assert result is not None
        assert result.lower() == "auto"

    def test_compound_with_fugen_s(self):
        # "Bundeswahl" — split at "s" Fugenelement → "wahl"
        concrete = _mock_concrete({"wahl"})
        result = compound_head("Bundeswahl", concrete, "N", _DE_CFG)
        assert result is not None
        assert result.lower() == "wahl"

    def test_no_compound_splitting_returns_none(self):
        concrete = _mock_concrete({"auto"})
        assert compound_head("Elektroauto", concrete, "N", _NO_CFG) is None

    def test_word_not_in_dict_returns_none(self):
        concrete = _mock_concrete(set())
        assert compound_head("Xyzabcdef", concrete, "N", _DE_CFG) is None

    def test_short_word_not_split(self):
        # "ab" (2 chars) is below minimum — can't be split meaningfully
        concrete = _mock_concrete({"ab"})
        result = compound_head("ab", concrete, "N", _DE_CFG)
        assert result is None

    def test_category_mismatch_not_returned(self):
        # Dict has "auto" as N but we ask for V — should not match
        def _lookup(w):
            if w.lower() == "auto":
                return [("auto_1_N", "Sg Nom", 1.0)]
            return []
        m = MagicMock()
        m.lookupMorpho.side_effect = _lookup
        result = compound_head("Elektroauto", m, "V", _DE_CFG)
        assert result is None

    def test_prefers_shortest_matching_head(self):
        # Both "kabel" and "labelkabel" are in dict; "kabel" (shorter) wins
        concrete = _mock_concrete({"kabel", "labelkabel"})
        result = compound_head("Ladekabel", concrete, "N", _DE_CFG)
        assert result is not None
        assert result.lower() == "kabel"
