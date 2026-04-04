"""
Unit tests for utility functions across translator modules.

All tests here are pure-Python with no external resources (no GF, no NMT).
"""
import pytest

from translator.gf_translator import _apply_surface_map, TranslationResult
from translator.wordnet import (
    _is_valid_translation,
    extract_lin_surface,
    _make_fun_name,
    _make_lin_expr,
)
from translator.keywords import _auto_topics


# ---------------------------------------------------------------------------
# _apply_surface_map
# ---------------------------------------------------------------------------

class TestApplySurfaceMap:
    def test_empty_map_passthrough(self):
        assert _apply_surface_map("hello world", {}) == "hello world"

    def test_empty_text(self):
        assert _apply_surface_map("", {"battery": "Batterie"}) == ""

    def test_replaces_known_word(self):
        result = _apply_surface_map("I have a battery", {"battery": "Batterie"})
        assert result == "I have a Batterie"

    def test_case_insensitive_lookup(self):
        result = _apply_surface_map("The Battery is dead", {"battery": "Batterie"})
        assert result == "The Batterie is dead"

    def test_preserves_trailing_punctuation(self):
        result = _apply_surface_map("I need a battery.", {"battery": "Batterie"})
        assert result == "I need a Batterie."

    def test_preserves_leading_punctuation(self):
        result = _apply_surface_map('"battery" matters', {"battery": "Batterie"})
        assert result == '"Batterie" matters'

    def test_no_partial_word_match(self):
        # "batteries" is not in the map — should not be replaced
        result = _apply_surface_map("I need batteries", {"battery": "Batterie"})
        assert result == "I need batteries"

    def test_multiple_replacements(self):
        result = _apply_surface_map(
            "charge the battery",
            {"battery": "Batterie", "charge": "laden"},
        )
        assert result == "laden the Batterie"

    def test_word_not_in_map_unchanged(self):
        result = _apply_surface_map("hello world", {"battery": "Batterie"})
        assert result == "hello world"


# ---------------------------------------------------------------------------
# TranslationResult
# ---------------------------------------------------------------------------

class TestTranslationResult:
    def test_str_returns_text(self):
        r = TranslationResult("hola", "gf")
        assert str(r) == "hola"

    def test_text_attribute(self):
        r = TranslationResult("hola", "gf")
        assert r.text == "hola"

    def test_method_gf(self):
        r = TranslationResult("hola", "gf")
        assert r.method == "gf"

    def test_method_nmt(self):
        r = TranslationResult("hola", "nmt")
        assert r.method == "nmt"

    def test_repr_contains_text_and_method(self):
        r = TranslationResult("hola", "gf")
        assert "hola" in repr(r)
        assert "gf" in repr(r)


# ---------------------------------------------------------------------------
# _is_valid_translation
# ---------------------------------------------------------------------------

class TestIsValidTranslation:
    def test_empty_string_invalid(self):
        assert not _is_valid_translation("")

    def test_whitespace_only_invalid(self):
        assert not _is_valid_translation("   ")

    def test_none_invalid(self):
        assert not _is_valid_translation(None)

    def test_repetitive_five_tokens_invalid(self):
        # len > 4 and unique ratio = 1/5 = 0.2 < 0.4
        assert not _is_valid_translation("ng ng ng ng ng")

    def test_four_identical_tokens_valid(self):
        # len == 4, threshold only applies when len > 4
        assert _is_valid_translation("ng ng ng ng")

    def test_normal_single_word_valid(self):
        assert _is_valid_translation("laufen")

    def test_normal_phrase_valid(self):
        assert _is_valid_translation("electric vehicle")

    def test_varied_five_tokens_valid(self):
        # unique ratio = 5/5 = 1.0 >= 0.4
        assert _is_valid_translation("the car runs on electricity")


# ---------------------------------------------------------------------------
# extract_lin_surface
# ---------------------------------------------------------------------------

class TestExtractLinSurface:
    def test_simple_mkN(self):
        assert extract_lin_surface('mkN "tree"') == "tree"

    def test_mkV2_mkV_returns_first_quoted(self):
        assert extract_lin_surface('mkV2 (mkV "run")') == "run"

    def test_variants_empty_returns_none(self):
        assert extract_lin_surface("variants {}") is None

    def test_umlaut_preserved(self):
        assert extract_lin_surface('mkN "Batterie"') == "Batterie"

    def test_mkA(self):
        assert extract_lin_surface('mkA "schnell"') == "schnell"


# ---------------------------------------------------------------------------
# _make_fun_name
# ---------------------------------------------------------------------------

class TestMakeFunName:
    def test_simple_word(self):
        assert _make_fun_name("battery", "N") == "battery_N"

    def test_hyphen_to_underscore(self):
        assert _make_fun_name("solid-state", "N") == "solid_state_N"

    def test_space_to_underscore(self):
        assert _make_fun_name("electric vehicle", "N") == "electric_vehicle_N"

    def test_digit_prefix_gets_n(self):
        result = _make_fun_name("3d", "N")
        assert result.startswith("n_"), f"Expected n_ prefix, got: {result}"

    def test_uppercase_lowercased(self):
        assert _make_fun_name("Battery", "N") == "battery_N"

    def test_verb_category(self):
        assert _make_fun_name("run", "V2") == "run_V2"


# ---------------------------------------------------------------------------
# _make_lin_expr
# ---------------------------------------------------------------------------

class TestMakeLinExpr:
    def test_spanish_ar_verb(self):
        assert _make_lin_expr("hablar", "V2", "es") == 'mkV2 (mkV "hablar")'

    def test_spanish_ir_verb(self):
        assert _make_lin_expr("vivir", "V2", "es") == 'mkV2 (mkV "vivir")'

    def test_spanish_invalid_verb_ending(self):
        # "xyz" doesn't end in ar/ir/er
        assert _make_lin_expr("xyz", "V2", "es") == "variants {}"

    def test_german_en_verb(self):
        assert _make_lin_expr("laufen", "V", "de") == 'mkV "laufen"'

    def test_german_invalid_verb_ending(self):
        assert _make_lin_expr("xyz", "V", "de") == "variants {}"

    def test_multi_word_returns_variants(self):
        # Multi-word can't be passed to GF paradigm functions
        assert _make_lin_expr("von Nutzen sein", "N", "de") == "variants {}"

    def test_japanese_zero_morph_noun(self):
        assert _make_lin_expr("電池", "N", "ja") == 'mkN "電池"'

    def test_japanese_zero_morph_v2(self):
        assert _make_lin_expr("走る", "V2", "ja") == 'mkV2 "走る"'

    def test_english_noun(self):
        assert _make_lin_expr("battery", "N", "en") == 'mkN "battery"'

    def test_english_verb_no_suffix_restriction(self):
        # English has no verb_suffixes restriction
        assert _make_lin_expr("run", "V", "en") == 'mkV "run"'


# ---------------------------------------------------------------------------
# _auto_topics
# ---------------------------------------------------------------------------

class TestAutoTopics:
    def test_min_bounds_respected(self):
        n_topics, n_words = _auto_topics(1, 10)
        assert n_topics >= 2
        assert n_words >= 5

    def test_max_bounds_respected(self):
        n_topics, n_words = _auto_topics(10000, 100000)
        assert n_topics <= 12
        assert n_words <= 20

    def test_returns_two_ints(self):
        result = _auto_topics(50, 500)
        assert len(result) == 2
        assert all(isinstance(x, int) for x in result)

    def test_scales_with_chunk_count(self):
        t_small, _ = _auto_topics(5, 50)
        t_large, _ = _auto_topics(200, 2000)
        assert t_large >= t_small
