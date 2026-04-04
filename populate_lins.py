"""
Populate missing lin columns in gf_wordnet.db from GF WordNet source files.

Priority chain for each target language:
  1. GF WordNet source  — WordNet{Suffix}.gf already has expert-written lin
                          expressions covering ~101-103k of 111k entries.
  2. NMT                — translate English surface → target for genuine GF
                          gaps (entries with variants {} or not present).

Apertium is not used here because the apertium.db is source→English only;
it does not have English→target translations needed for this direction.

Usage:
    # First time, for all configured languages:
    python populate_lins.py

    # Add a new language later:
    python populate_lins.py --lang de

    # Override gf-wordnet source directory:
    python populate_lins.py --wordnet-dir /path/to/gf-wordnet

    # Skip NMT fallback (GF source only):
    python populate_lins.py --no-nmt

gf-wordnet source:
    The script reads WordNet{Suffix}.gf files from the gf-wordnet repo.
    Default location: ./resources/gf-wordnet/
    Clone with: git clone --depth 1 https://github.com/GrammaticalFramework/gf-wordnet.git resources/gf-wordnet
"""

import argparse
import re
import sqlite3
import sys
from pathlib import Path

DB_PATH = "./gf_wordnet.db"
GF_WORDNET_DIR = "./resources/gf-wordnet"

BATCH_SIZE = 64
COMMIT_EVERY = 10  # commit after every N batches (~640 rows)

# Languages to populate — maps iso code → (db_column, gf_file_suffix)
# Only languages NOT already in the DB schema belong here.
POPULATE_LANGS = {
    "de": ("ger_lin", "Ger"),
    "ja": ("jpn_lin", "Jpn"),
}

from translator.wordnet import extract_lin_surface, _make_lin_expr
from translator.nmt import translate_batch


def _parse_wordnet_gf(gf_path: Path) -> dict:
    """
    Parse a WordNet{Lang}.gf file and return {fun_name: lin_expr}.

    Skips entries with 'variants {}' (no linearization in this language).
    Strips trailing comments (e.g., '; --guessed') from expressions.
    Only single-line lin entries are handled; the one known multi-line
    entry (the_only_Quant) is a structural word not in our content categories.
    """
    lins = {}
    pattern = re.compile(r'^lin (\S+) = (.+?) *;')
    with open(gf_path, encoding="utf-8") as f:
        for line in f:
            m = pattern.match(line)
            if not m:
                continue
            fun_name = m.group(1)
            expr = m.group(2).rstrip()
            if expr == "variants {}":
                continue
            lins[fun_name] = expr
    return lins


def _add_column_if_missing(conn: sqlite3.Connection, column: str):
    """Add a TEXT column to functions table if it doesn't already exist."""
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(functions)")
    existing = {row[1] for row in cur.fetchall()}
    if column not in existing:
        cur.execute(f"ALTER TABLE functions ADD COLUMN {column} TEXT")
        conn.commit()
        print(f"  Added column '{column}' to functions table.")
    else:
        print(f"  Column '{column}' already exists.")


def populate_lang(lang: str, db_column: str, gf_suffix: str,
                  conn: sqlite3.Connection, wordnet_dir: Path,
                  use_nmt: bool):
    gf_path = wordnet_dir / f"WordNet{gf_suffix}.gf"
    if not gf_path.exists():
        print(f"  ERROR: {gf_path} not found. Clone gf-wordnet first.")
        print(f"    git clone --depth 1 https://github.com/GrammaticalFramework/gf-wordnet.git resources/gf-wordnet")
        return

    print(f"\n[{lang}] Parsing {gf_path.name}...")
    gf_lins = _parse_wordnet_gf(gf_path)
    print(f"  {len(gf_lins):,} non-empty lin entries found in GF source.")

    _add_column_if_missing(conn, db_column)

    cur = conn.cursor()

    # Fetch all rows that still need this column populated
    cur.execute(f"""
        SELECT id, fun_name, category, eng_lin
        FROM functions
        WHERE ({db_column} IS NULL OR {db_column} = '' OR {db_column} = 'variants {{}}')
    """)
    rows = cur.fetchall()
    total = len(rows)
    print(f"  {total:,} rows need {db_column}.")

    # --- Pass 1: GF source ---
    gf_hits = 0
    nmt_needed = []  # (id, category, english_surface)

    for row_id, fun_name, category, eng_lin in rows:
        lin = gf_lins.get(fun_name)
        if lin:
            cur.execute(f"UPDATE functions SET {db_column} = ? WHERE id = ?",
                        (lin, row_id))
            gf_hits += 1
        else:
            # Prepare for NMT fallback if we have an English surface
            surface = extract_lin_surface(eng_lin) if eng_lin else None
            if surface:
                nmt_needed.append((row_id, category, surface))

    conn.commit()
    print(f"  GF source:  {gf_hits:,} entries populated.")
    print(f"  Remaining:  {len(nmt_needed):,} entries need NMT fallback.")

    if not use_nmt or not nmt_needed:
        return

    # --- Pass 2: NMT fallback ---
    print(f"  NMT fallback: translating {len(nmt_needed):,} English surfaces → {lang.upper()}...")
    done = errors = 0
    batch_count = 0

    for i in range(0, len(nmt_needed), BATCH_SIZE):
        batch = nmt_needed[i: i + BATCH_SIZE]
        surfaces = [row[2] for row in batch]

        try:
            translations = translate_batch(surfaces, "en", lang)
        except Exception as e:
            print(f"  Batch {batch_count + 1} failed: {e}", file=sys.stderr)
            errors += len(batch)
            batch_count += 1
            continue

        for (row_id, category, _), translated in zip(batch, translations):
            if translated and translated.strip():
                lin_expr = _make_lin_expr(translated.strip(), category, lang)
                cur.execute(f"UPDATE functions SET {db_column} = ? WHERE id = ?",
                            (lin_expr, row_id))
                done += 1

        batch_count += 1
        if batch_count % COMMIT_EVERY == 0:
            conn.commit()
            pct = (i + len(batch)) / len(nmt_needed) * 100
            print(f"  [{pct:5.1f}%] {done} NMT entries added, {errors} errors")

    conn.commit()
    print(f"  NMT fallback: {done:,} entries populated, {errors} errors.")

    cur.execute(f"SELECT COUNT(*) FROM functions WHERE {db_column} IS NOT NULL AND {db_column} != '' AND {db_column} != 'variants {{}}'")
    final = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM functions")
    total_rows = cur.fetchone()[0]
    print(f"\n[{lang}] Done. Total populated {db_column}: {final:,} / {total_rows:,}")


def main():
    parser = argparse.ArgumentParser(description="Populate ger_lin/jpn_lin in gf_wordnet.db from GF WordNet source")
    parser.add_argument(
        "--lang", nargs="+", default=list(POPULATE_LANGS.keys()),
        choices=list(POPULATE_LANGS.keys()),
        help="Languages to populate (default: all)"
    )
    parser.add_argument("--db", default=DB_PATH, help=f"DB path (default: {DB_PATH})")
    parser.add_argument(
        "--wordnet-dir", default=GF_WORDNET_DIR,
        help=f"Path to gf-wordnet repo (default: {GF_WORDNET_DIR})"
    )
    parser.add_argument(
        "--no-nmt", action="store_true",
        help="Skip NMT fallback (GF source only)"
    )
    args = parser.parse_args()

    wordnet_dir = Path(args.wordnet_dir)
    if not wordnet_dir.exists():
        print(f"ERROR: gf-wordnet directory not found at {wordnet_dir}")
        print("Clone it first:")
        print(f"  git clone --depth 1 https://github.com/GrammaticalFramework/gf-wordnet.git {wordnet_dir}")
        sys.exit(1)

    conn = sqlite3.connect(args.db)

    for lang in args.lang:
        db_column, gf_suffix = POPULATE_LANGS[lang]
        populate_lang(lang, db_column, gf_suffix, conn, wordnet_dir, use_nmt=not args.no_nmt)

    conn.close()


if __name__ == "__main__":
    main()
