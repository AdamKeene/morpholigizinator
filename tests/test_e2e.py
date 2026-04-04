"""
End-to-end tests for translate_document across language pairs.

These tests exercise the full pipeline: keyword extraction, GF lookup,
Wiktionary, Apertium, NMT fallback, and grammar compilation.

Requirements:
    - GF binary on PATH
    - Parse.pgf compiled for relevant languages
    - NMT models (downloaded automatically by HuggingFace on first run)
    - resources/wiktionary.db and resources/apertium.db
    - resources/madagascar_srt/madagascar.srt
    - resources/sample_document_{en,de,ja}.txt
    - FastText vectors (resources/cc.*.300.vec)

Run with:
    pytest -m slow
"""
from pathlib import Path
import pytest


def _skip_if_missing(*paths):
    for p in paths:
        if not Path(p).exists():
            pytest.skip(f"Resource not found: {p}")


# ---------------------------------------------------------------------------
# Translator fixtures  (module-scoped so grammar compiles once per class)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def es_en_translator():
    _skip_if_missing("resources/madagascar_srt/madagascar.srt")
    from translator import translate_document
    return translate_document(
        "resources/madagascar_srt/madagascar.srt", "es", "en", verbose=False
    )


@pytest.fixture(scope="module")
def en_es_translator():
    _skip_if_missing("resources/sample_document_en.txt")
    from translator import translate_document
    return translate_document(
        "resources/sample_document_en.txt", "en", "es", verbose=False
    )


@pytest.fixture(scope="module")
def en_de_translator():
    _skip_if_missing("resources/sample_document_en.txt")
    from translator import translate_document
    return translate_document(
        "resources/sample_document_en.txt", "en", "de", verbose=False
    )


@pytest.fixture(scope="module")
def de_en_translator():
    _skip_if_missing("resources/sample_document_de.txt")
    from translator import translate_document
    return translate_document(
        "resources/sample_document_de.txt", "de", "en", verbose=False
    )


@pytest.fixture(scope="module")
def de_es_translator():
    _skip_if_missing("resources/sample_document_de.txt")
    from translator import translate_document
    return translate_document(
        "resources/sample_document_de.txt", "de", "es", verbose=False
    )


@pytest.fixture(scope="module")
def ja_en_translator():
    _skip_if_missing("resources/sample_document_ja.txt")
    from translator import translate_document
    return translate_document(
        "resources/sample_document_ja.txt", "ja", "en", verbose=False
    )


# ---------------------------------------------------------------------------
# Spanish → English  (Madagascar domain)
# ---------------------------------------------------------------------------

@pytest.mark.slow
class TestEsToEn:
    def test_returns_nonempty(self, es_en_translator):
        result = es_en_translator("el pingüino corre")
        assert str(result).strip()

    def test_method_recorded(self, es_en_translator):
        result = es_en_translator("el pingüino corre")
        assert result.method in ("gf", "nmt")

    def test_wordnet_phrase(self, es_en_translator):
        # "Se ve tan triste" — all WordNet words
        result = es_en_translator("Se ve tan triste")
        assert str(result).strip()

    def test_nmt_fallback_for_slang(self, es_en_translator):
        # "mi troca" — Mexican slang for truck, GF can't parse this
        result = es_en_translator("mi troca")
        assert str(result).strip()


# ---------------------------------------------------------------------------
# English → Spanish  (EV domain)
# ---------------------------------------------------------------------------

@pytest.mark.slow
class TestEnToEs:
    def test_battery_phrase(self, en_es_translator):
        result = en_es_translator("the battery charges quickly")
        assert str(result).strip()
        assert result.method in ("gf", "nmt")

    def test_car_runs(self, en_es_translator):
        result = en_es_translator("the car runs on electricity")
        assert str(result).strip()

    def test_domain_term_handled(self, en_es_translator):
        result = en_es_translator("solid state battery")
        assert str(result).strip()


# ---------------------------------------------------------------------------
# English → German  (EV domain)
# ---------------------------------------------------------------------------

@pytest.mark.slow
class TestEnToDe:
    def test_battery_phrase(self, en_de_translator):
        result = en_de_translator("the battery charges quickly")
        assert str(result).strip()
        assert result.method in ("gf", "nmt")

    def test_car_phrase(self, en_de_translator):
        result = en_de_translator("the car runs on electricity")
        assert str(result).strip()


# ---------------------------------------------------------------------------
# German → English  (EV domain)
# ---------------------------------------------------------------------------

@pytest.mark.slow
class TestDeToEn:
    def test_battery_phrase(self, de_en_translator):
        result = de_en_translator("die Batterie lädt schnell")
        assert str(result).strip()

    def test_car_phrase(self, de_en_translator):
        result = de_en_translator("das Auto fährt elektrisch")
        assert str(result).strip()


# ---------------------------------------------------------------------------
# German → Spanish  (EV domain)
# ---------------------------------------------------------------------------

@pytest.mark.slow
class TestDeToEs:
    def test_battery_phrase(self, de_es_translator):
        result = de_es_translator("die Batterie lädt schnell")
        assert str(result).strip()


# ---------------------------------------------------------------------------
# Japanese → English  (EV domain)
# ---------------------------------------------------------------------------

@pytest.mark.slow
class TestJaToEn:
    def test_electric_vehicle(self, ja_en_translator):
        # 電気自動車 — should resolve via GF WordNet
        result = ja_en_translator("電気自動車")
        assert str(result).strip()
        assert result.method in ("gf", "nmt")

    def test_domain_term_handled(self, ja_en_translator):
        # バッテリーパック — domain NMT
        result = ja_en_translator("バッテリーパック")
        assert str(result).strip()
