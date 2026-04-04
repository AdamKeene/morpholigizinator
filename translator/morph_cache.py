"""
In-process morphological form cache for GF bare-word linearization results.

Caches the output of _bare_word() calls so that repeated lesson-generation
requests for the same vocabulary skip tabularLinearize/linearize against the
C library.  The cache persists for the lifetime of the Python process —
warm across web requests in a long-running server.

For pre-population across process restarts, build the SQLite backing store
once with:

    python build_morph_cache.py [--langs de] [--pgf ./Parse.pgf]

Schema (resources/morph_cache.db):
    bare_words(
        fun_name TEXT NOT NULL,   -- GF function name, e.g. "car_1_N"
        gf_cat   TEXT NOT NULL,   -- "N" | "V" | "V2" | "A" | "Adv"
        lang     TEXT NOT NULL,   -- ISO-639-1 code ("en", "de", …)
        surface  TEXT NOT NULL,   -- dictionary/citation form surface string
        PRIMARY KEY (fun_name, gf_cat, lang)
    )
"""

import sqlite3
from pathlib import Path
from typing import Optional

MORPH_CACHE_DB = "./resources/morph_cache.db"

# In-process cache: (fun_name, gf_cat, lang) → surface_form
_cache: dict = {}
_db_loaded: bool = False


def get(fun_name: str, gf_cat: str, lang: str) -> Optional[str]:
    """Return cached surface form, or None if not in cache."""
    key = (fun_name, gf_cat, lang)
    hit = _cache.get(key)
    if hit is not None:
        return hit
    _load_db_once()
    return _cache.get(key)


def put(fun_name: str, gf_cat: str, lang: str, surface: str) -> None:
    """Store a surface form in the in-process cache (not persisted to DB)."""
    _cache[(fun_name, gf_cat, lang)] = surface


def _load_db_once() -> None:
    global _db_loaded
    if _db_loaded:
        return
    _db_loaded = True

    db_path = Path(MORPH_CACHE_DB)
    if not db_path.exists():
        return

    try:
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        cur = conn.cursor()
        cur.execute("SELECT fun_name, gf_cat, lang, surface FROM bare_words")
        for row in cur.fetchall():
            _cache[(row[0], row[1], row[2])] = row[3]
        conn.close()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("morph_cache: failed to load DB: %s", e)


def write_db(entries: list, db_path: str = MORPH_CACHE_DB) -> int:
    """
    Write (fun_name, gf_cat, lang, surface) tuples to the SQLite backing store.
    Used by build_morph_cache.py.  Returns the number of rows written.
    """
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    cur = conn.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS bare_words (
            fun_name TEXT NOT NULL,
            gf_cat   TEXT NOT NULL,
            lang     TEXT NOT NULL,
            surface  TEXT NOT NULL,
            PRIMARY KEY (fun_name, gf_cat, lang)
        );
    """)
    cur.executemany(
        "INSERT OR REPLACE INTO bare_words (fun_name, gf_cat, lang, surface) VALUES (?,?,?,?)",
        entries,
    )
    conn.commit()
    n = cur.execute("SELECT COUNT(*) FROM bare_words").fetchone()[0]
    conn.close()
    return n
