"""
Shared fixtures for the morpholigizinator test suite.

Fixture tiers:
    unit        — no external deps, always available
    integration — requires Parse.pgf on disk; fixtures skip automatically if absent
    slow        — requires GF binary, NMT models, full pipeline resources
"""
from pathlib import Path
import pytest

PARSE_PGF = "./Parse.pgf"


# ---------------------------------------------------------------------------
# Marker registration (suppresses pytest unknown-marker warnings)
# ---------------------------------------------------------------------------

def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "integration: requires Parse.pgf on disk (~1s to load, then fast)"
    )
    config.addinivalue_line(
        "markers",
        "slow: requires GF binary, NMT models, and full pipeline resources (minutes)"
    )


# ---------------------------------------------------------------------------
# Parse.pgf fixtures  (session-scoped — loaded once for the whole test run)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def parse_pgf_path():
    p = Path(PARSE_PGF)
    if not p.exists():
        pytest.skip(f"Parse.pgf not found at {PARSE_PGF} — skipping integration tests")
    return str(p)


@pytest.fixture(scope="session")
def grammar(parse_pgf_path):
    from translator.pipeline import _load_parse_grammar
    return _load_parse_grammar(parse_pgf_path)


@pytest.fixture(scope="session")
def concretes(grammar):
    """Return {lang: pgf.Concr} for en/es/de from Parse.pgf."""
    from translator.config import LANG_CONFIG
    result = {}
    for lang in ("en", "es", "de"):
        suffix = LANG_CONFIG[lang]["gf_suffix"]
        c = grammar.languages.get(f"Parse{suffix}")
        if c:
            result[lang] = c
    return result


@pytest.fixture(scope="session")
def lesson_entries(grammar, parse_pgf_path):
    """
    A small build_lesson result shared across integration tests.
    Source text is chosen so "battery" and "charge" each appear in context,
    giving the sense-selection parser real sentences to boost from.
    """
    from translator.generator import build_lesson
    vocab = {"battery": "N", "charge": "V2", "run": "V", "fast": "A"}
    text = (
        "The battery charges quickly. "
        "The battery is lightweight and reliable. "
        "I charge it every day before the trip. "
        "The car runs fast on the highway."
    )
    return build_lesson(vocab, text, "en", ["es", "de"], pgf_path=parse_pgf_path)
