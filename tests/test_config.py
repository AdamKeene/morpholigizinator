"""
Unit tests for translator/config.py.

Validates structure invariants that must hold for the pipeline and GF writer
to function correctly.  No external resources required.
"""
import pytest
from translator.config import LANG_CONFIG, MARIAN_MODELS

REQUIRED_KEYS = {
    "spacy_model", "fasttext_vec", "gf_suffix",
    "gf_cat_module", "gf_open", "gf_zero_morph",
}


@pytest.mark.parametrize("lang", list(LANG_CONFIG.keys()))
def test_lang_config_required_keys(lang):
    missing = REQUIRED_KEYS - set(LANG_CONFIG[lang].keys())
    assert not missing, f"LANG_CONFIG['{lang}'] is missing keys: {missing}"


def test_gf_suffixes_unique():
    suffixes = [cfg["gf_suffix"] for cfg in LANG_CONFIG.values()]
    assert len(suffixes) == len(set(suffixes)), \
        f"Duplicate gf_suffix values: {suffixes}"


@pytest.mark.parametrize("lang", list(LANG_CONFIG.keys()))
def test_gf_zero_morph_is_bool(lang):
    assert isinstance(LANG_CONFIG[lang]["gf_zero_morph"], bool), \
        f"gf_zero_morph must be bool for '{lang}'"


@pytest.mark.parametrize("lang", list(LANG_CONFIG.keys()))
def test_gf_suffix_nonempty(lang):
    assert LANG_CONFIG[lang]["gf_suffix"].strip(), \
        f"gf_suffix is empty for '{lang}'"


@pytest.mark.parametrize("key", list(MARIAN_MODELS.keys()))
def test_marian_model_key_format(key):
    parts = key.split("-")
    assert len(parts) == 2, f"Expected 'src-tgt' format: {key!r}"
    src, tgt = parts
    assert src in LANG_CONFIG, f"Unknown source lang {src!r} in MARIAN_MODELS key {key!r}"
    assert tgt in LANG_CONFIG, f"Unknown target lang {tgt!r} in MARIAN_MODELS key {key!r}"


def test_marian_models_no_self_translation():
    for key in MARIAN_MODELS:
        src, tgt = key.split("-")
        assert src != tgt, f"Self-translation model registered: {key!r}"
