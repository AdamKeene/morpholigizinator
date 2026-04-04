"""
JMdict lookup for Japanese vocabulary.

JMdict (Jim Breen's Japanese-Multilingual Dictionary) provides ~170k Japanese
entries with glosses in English, German, French, Spanish and other languages.
It covers modern Japanese vocabulary far more comprehensively than GF WordNet,
including compound verbs, する-verbs, colloquialisms, and technical terms.

Role in the pipeline
--------------------
Sits between the GF lookupMorpho step and Wiktionary in the lookup chain,
but only activates when the source language is Japanese.  For a Japanese word
not found in ParseJpn, JMdict returns target-language surface forms that can
be used to build GF DomainLexicon entries (via _make_lin_expr / NMT fill-in).

Unlike Wiktionary (which gives source → English bridge), JMdict gives
Japanese → {English, German, Spanish, French, ...} directly, eliminating one
NMT translation step for Japanese.

DB schema (built by build_jmdict_db.py)
----------------------------------------
    entries(
        id        INTEGER PRIMARY KEY,
        kanji     TEXT,      -- primary kanji form; empty for kana-only entries
        reading   TEXT,      -- primary hiragana/katakana reading
        pos       TEXT,      -- GF category: N | V | V2 | A | Adv
        sense_idx INTEGER,   -- 0-based sense index within the entry
        gloss_en  TEXT,      -- English gloss (always present)
        gloss_de  TEXT,      -- German gloss (may be NULL)
        gloss_es  TEXT,      -- Spanish gloss (may be NULL)
        gloss_fr  TEXT,      -- French gloss (may be NULL)
    )
    CREATE INDEX idx_kanji   ON entries(kanji);
    CREATE INDEX idx_reading ON entries(reading);

Lookup strategy
---------------
Given a Japanese surface form, we look up by kanji first, then by reading.
The best sense (sense_idx=0, or whichever has the most glosses) is used.
A single-word English gloss is extracted to build the GF fun_name (mirroring
how Wiktionary uses English as the canonical identifier).
"""

import sqlite3
from pathlib import Path
from typing import Dict, List, Optional

from .config import LANG_CONFIG
from .wordnet import _make_fun_name, _make_lin_expr

JMDICT_DB = "./resources/jmdict.db"

# JMdict lang codes → our ISO-639-1 codes
_JMDICT_LANG_MAP = {
    "eng": "en",
    "ger": "de",
    "spa": "es",
    "fre": "fr",
    "rus": "ru",
    "nld": "nl",
    "hun": "hu",
    "slv": "sl",
}


class JMdictLookup:
    """
    SQLite-backed JMdict lookup for Japanese → target-language vocabulary.

    Only activated when the source language is Japanese.  Falls back
    gracefully (returns all words as unresolved) when the DB is absent.

    Build the DB once with:
        python build_jmdict_db.py
    """

    def __init__(self, db_path: str = JMDICT_DB):
        self._db_path   = db_path
        self._available = Path(db_path).exists()
        if not self._available:
            print(f"  JMdict DB not found at {db_path} — skipping. "
                  f"Run build_jmdict_db.py to build it.")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def lookup_word(
        self,
        word: str,
        target_langs: List[str],
    ) -> Optional[Dict[str, str]]:
        """
        Look up a single Japanese word and return {target_lang: gloss}.

        Tries kanji lookup first, then reading (kana) lookup.
        Returns only the primary sense (sense_idx = 0).
        Returns None if the word is not in the DB.
        """
        if not self._available:
            return None

        conn = sqlite3.connect(self._db_path)
        cur  = conn.cursor()

        row = self._fetch_best(cur, word, target_langs)
        conn.close()
        return row

    def build_entries(
        self,
        words_cats: Dict[str, str],
        source_lang: str,
        target_langs: List[str],
    ):
        """
        Look up a batch of Japanese words and build GF entry dicts for hits.

        Only operates when source_lang == "ja".  Returns
        (jmdict_entries, remaining_words_cats) in the same shape as
        WiktionaryLookup.build_entries().

        fun_name is keyed on the English gloss (consistent with WordNet
        naming).  The source Japanese surface form is stored as the
        source-language lin so ParseJpn can use it at runtime.
        """
        if not self._available or not words_cats or source_lang != "ja":
            return [], dict(words_cats)

        conn    = sqlite3.connect(self._db_path)
        cur     = conn.cursor()
        entries = []
        remaining = {}

        for word, cat in words_cats.items():
            row = self._fetch_best(cur, word, target_langs)
            if row is None:
                remaining[word] = cat
                continue

            en_gloss = row.get("en")
            if not en_gloss:
                remaining[word] = cat
                continue

            lins = {
                lang: _make_lin_expr(gloss, cat, lang)
                for lang, gloss in row.items()
                if lang in LANG_CONFIG and gloss
            }
            # Always include the source Japanese form as the source-lang lin
            if source_lang not in lins:
                lins[source_lang] = _make_lin_expr(word, cat, source_lang)

            fun_name = _make_fun_name(en_gloss, cat)
            entries.append({
                "fun_name":  fun_name,
                "category":  cat,
                "src_word":  en_gloss,
                "lins":      lins,
            })

        conn.close()
        return entries, remaining

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fetch_best(
        self,
        cur: sqlite3.Cursor,
        word: str,
        target_langs: List[str],
    ) -> Optional[Dict[str, str]]:
        """
        Return {lang: gloss} for the best matching entry, or None.

        Tries kanji match first, then reading match.  Within each, picks
        sense_idx=0 (primary sense).  Only returns rows where at least one
        target language has a non-NULL gloss.
        """
        for col in ("kanji", "reading"):
            cur.execute(
                "SELECT gloss_en, gloss_de, gloss_es, gloss_fr "
                "FROM entries WHERE ? = ? AND sense_idx = 0 "
                "ORDER BY id LIMIT 1",
                (col, word),
            )
            row = cur.fetchone()
            if row:
                gloss_en, gloss_de, gloss_es, gloss_fr = row
                result: Dict[str, str] = {}
                _maybe(result, "en", gloss_en)
                _maybe(result, "de", gloss_de)
                _maybe(result, "es", gloss_es)
                _maybe(result, "fr", gloss_fr)
                # Only return if at least one target language has a gloss
                if any(lang in result for lang in target_langs):
                    return result

        return None


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _maybe(d: dict, key: str, value: Optional[str]) -> None:
    if value:
        d[key] = value
