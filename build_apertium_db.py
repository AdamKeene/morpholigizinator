"""
Downloads Apertium bilingual .dix files and builds a local SQLite lookup DB.

Run from the project root:
    python build_apertium_db.py

DB is written to resources/apertium.db.
Re-running is safe — existing data for a language pair is replaced.
"""

import sqlite3
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

DB_PATH = "./resources/apertium.db"

# Apertium GitHub raw URLs for bilingual .dix files.
# Key format: (source_lang, target_lang)
DIX_URLS = {
    ("es", "en"): "https://raw.githubusercontent.com/apertium/apertium-es-en/master/apertium-es-en.es-en.dix",
    ("de", "en"): "https://raw.githubusercontent.com/apertium/apertium-de-en/master/apertium-de-en.de-en.dix",
    ("en", "es"): "https://raw.githubusercontent.com/apertium/apertium-es-en/master/apertium-es-en.es-en.dix",
    ("en", "de"): "https://raw.githubusercontent.com/apertium/apertium-de-en/master/apertium-de-en.de-en.dix",
}

CACHE_DIR = Path("./resources/apertium_cache")


def _fetch_dix(url, pair_key):
    """Download a .dix file, caching locally."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{pair_key[0]}-{pair_key[1]}.dix"
    cached = CACHE_DIR / filename
    if cached.exists():
        print(f"  Using cached {filename}")
        return cached.read_text(encoding="utf-8")
    print(f"  Downloading {url} ...")
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    cached.write_text(resp.text, encoding="utf-8")
    return resp.text


def _parse_dix(xml_text, source_lang, target_lang):
    """
    Parse an Apertium .dix file and yield (source_lemma, target_lemma, pos) tuples.

    The .dix format is bidirectional: <l> is the left language, <r> the right.
    For es-en the file is always es (left) → en (right).
    For en-es we swap l/r when iterating.
    """
    root = ET.fromstring(xml_text)
    swap = source_lang == "en"  # en-es uses the same file with sides swapped

    for entry in root.iter("e"):
        p = entry.find("p")
        if p is None:
            continue
        l_el = p.find("l")
        r_el = p.find("r")
        if l_el is None or r_el is None:
            continue

        # Skip multi-word entries (contain <b/> blank elements)
        if l_el.find("b") is not None or r_el.find("b") is not None:
            continue

        src_el, tgt_el = (r_el, l_el) if swap else (l_el, r_el)

        src_lemma = src_el.text
        tgt_lemma = tgt_el.text
        if not src_lemma or not tgt_lemma:
            continue

        src_lemma = src_lemma.strip()
        tgt_lemma = tgt_lemma.strip()
        if not src_lemma or not tgt_lemma:
            continue

        # POS from first <s> child of source element
        s_el = src_el.find("s")
        pos = s_el.get("n") if s_el is not None else None

        yield src_lemma, tgt_lemma, pos


def build_db(pairs=None):
    """Build the SQLite DB for the given language pairs (default: all configured)."""
    if pairs is None:
        pairs = list(DIX_URLS.keys())

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS mappings (
            source_lang  TEXT NOT NULL,
            source_lemma TEXT NOT NULL,
            target_lang  TEXT NOT NULL,
            target_lemma TEXT NOT NULL,
            pos          TEXT
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_src ON mappings (source_lang, lower(source_lemma))")

    for pair in pairs:
        src, tgt = pair
        url = DIX_URLS.get(pair)
        if not url:
            print(f"  No .dix URL configured for {src}-{tgt}, skipping.")
            continue

        print(f"\nProcessing {src}→{tgt}...")
        try:
            xml_text = _fetch_dix(url, (src, tgt))
        except Exception as e:
            print(f"  Failed to fetch: {e}", file=sys.stderr)
            continue

        # Clear existing entries for this pair before re-inserting
        cur.execute("DELETE FROM mappings WHERE source_lang=? AND target_lang=?", (src, tgt))

        count = 0
        for src_lemma, tgt_lemma, pos in _parse_dix(xml_text, src, tgt):
            cur.execute(
                "INSERT INTO mappings (source_lang, source_lemma, target_lang, target_lemma, pos) VALUES (?,?,?,?,?)",
                (src, src_lemma, tgt, tgt_lemma, pos),
            )
            count += 1

        conn.commit()
        print(f"  {count:,} entries inserted for {src}→{tgt}")

    conn.close()
    print(f"\nDone. DB written to {DB_PATH}")


if __name__ == "__main__":
    build_db()
