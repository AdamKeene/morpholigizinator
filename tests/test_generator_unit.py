"""
Unit tests for pure functions in translator/generator.py.

No GF grammar or external resources required.
"""
import pytest
from translator.generator import (
    _extract_sense_number,
    _cat_matches,
    _translation_fingerprint,
)


# ---------------------------------------------------------------------------
# _extract_sense_number
# ---------------------------------------------------------------------------

class TestExtractSenseNumber:
    @pytest.mark.parametrize("fn, expected", [
        ("battery_1_N",     1),
        ("charge_10_N",     10),
        ("chargeFem_7_N",   7),
        ("have_10_V2",      10),
        ("run_1_V",         1),
        ("fast_1_A",        1),
        ("quickly_3_Adv",   3),
        # No standard sense pattern → sentinel 999
        ("charge_off_V",    999),
        ("thing",           999),
        ("PN",              999),
    ])
    def test_sense_number(self, fn, expected):
        assert _extract_sense_number(fn) == expected

    def test_lower_sense_sorts_earlier(self):
        fns = ["charge_10_N", "charge_3_N", "charge_1_N"]
        assert sorted(fns, key=_extract_sense_number) == [
            "charge_1_N", "charge_3_N", "charge_10_N"
        ]


# ---------------------------------------------------------------------------
# _cat_matches
# ---------------------------------------------------------------------------

class TestCatMatches:
    @pytest.mark.parametrize("fn, cat, expected", [
        ("battery_1_N",    "N",   True),
        ("battery_1_N",    "V",   False),
        ("battery_1_N",    "V2",  False),
        ("run_1_V",        "V",   True),
        ("run_1_V",        "N",   False),
        ("run_1_V",        "V2",  False),
        ("have_10_V2",     "V2",  True),
        ("have_10_V2",     "V",   False),
        ("fast_1_A",       "A",   True),
        ("fast_1_A",       "N",   False),
        ("quickly_1_Adv",  "Adv", True),
        ("quickly_1_Adv",  "A",   False),
    ])
    def test_matches(self, fn, cat, expected):
        assert _cat_matches(fn, cat) is expected


# ---------------------------------------------------------------------------
# _translation_fingerprint
# ---------------------------------------------------------------------------

class TestTranslationFingerprint:
    def test_excludes_source_lang(self):
        translations = {"en": "battery", "de": "Batterie", "es": "batería"}
        fp = _translation_fingerprint(translations, "en")
        langs = {pair[0] for pair in fp}
        assert "en" not in langs

    def test_includes_target_langs(self):
        translations = {"en": "battery", "de": "Batterie", "es": "batería"}
        fp = _translation_fingerprint(translations, "en")
        langs = {pair[0] for pair in fp}
        assert langs == {"de", "es"}

    def test_result_is_sorted(self):
        translations = {"en": "battery", "es": "batería", "de": "Batterie"}
        fp = _translation_fingerprint(translations, "en")
        langs = [pair[0] for pair in fp]
        assert langs == sorted(langs)

    def test_values_are_lowercased(self):
        translations = {"en": "Battery", "de": "BATTERIE"}
        fp = _translation_fingerprint(translations, "en")
        vals = {pair[1] for pair in fp}
        assert all(v == v.lower() for v in vals)

    def test_no_src_lang_includes_all(self):
        translations = {"de": "Batterie", "es": "batería"}
        fp = _translation_fingerprint(translations, None)
        langs = {pair[0] for pair in fp}
        assert langs == {"de", "es"}

    def test_empty_dict_returns_empty_tuple(self):
        assert _translation_fingerprint({}, "en") == ()

    def test_same_translations_same_fingerprint(self):
        t1 = {"en": "battery", "de": "Batterie", "es": "batería"}
        t2 = {"en": "battery", "de": "batterie", "es": "Batería"}  # different case
        fp1 = _translation_fingerprint(t1, "en")
        fp2 = _translation_fingerprint(t2, "en")
        assert fp1 == fp2

    def test_different_translations_different_fingerprint(self):
        t1 = {"en": "charge", "de": "laden", "es": "cargar"}
        t2 = {"en": "charge", "de": "Anklage", "es": "cargo"}
        fp1 = _translation_fingerprint(t1, "en")
        fp2 = _translation_fingerprint(t2, "en")
        assert fp1 != fp2
