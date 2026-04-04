"""
One-time script to fill NULL spa_lin entries in gf_wordnet.db by translating
English surface forms to Spanish via NMT.

Run from the project root:
    python populate_spa_lins.py

Commits every COMMIT_EVERY batches so progress is preserved on interruption.
Re-running is safe — only rows still missing spa_lin are touched.
"""

import sqlite3
import sys

DB_PATH = "./gf_wordnet.db"
BATCH_SIZE = 64
COMMIT_EVERY = 10  # commit after every N batches (~640 rows)

from translator.wordnet import extract_lin_surface, _make_lin_expr
from translator.nmt import translate_batch


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        SELECT id, category, eng_lin
        FROM functions
        WHERE (spa_lin IS NULL OR spa_lin = '' OR spa_lin = 'variants {}')
          AND eng_lin IS NOT NULL AND eng_lin != '' AND eng_lin != 'variants {}'
    """)
    rows = cur.fetchall()
    total = len(rows)
    print(f"Entries to populate: {total}")

    # Extract surface forms; skip rows where eng_lin has no parseable surface
    to_translate = []
    for row_id, category, eng_lin in rows:
        surface = extract_lin_surface(eng_lin)
        if surface:
            to_translate.append((row_id, category, surface))

    print(f"  {len(to_translate)} have parseable English surfaces ({total - len(to_translate)} skipped)\n")

    done = 0
    batch_count = 0
    errors = 0

    for i in range(0, len(to_translate), BATCH_SIZE):
        batch = to_translate[i : i + BATCH_SIZE]
        surfaces = [row[2] for row in batch]

        try:
            translations = translate_batch(surfaces, "en", "es")
        except Exception as e:
            print(f"  Batch {batch_count + 1} failed: {e}", file=sys.stderr)
            errors += len(batch)
            batch_count += 1
            continue

        for (row_id, category, _), spa_surface in zip(batch, translations):
            if spa_surface and spa_surface.strip():
                lin_expr = _make_lin_expr(spa_surface.strip(), category, "es")
                cur.execute(
                    "UPDATE functions SET spa_lin = ? WHERE id = ?",
                    (lin_expr, row_id),
                )
                done += 1

        batch_count += 1
        if batch_count % COMMIT_EVERY == 0:
            conn.commit()
            pct = (i + len(batch)) / len(to_translate) * 100
            print(f"  [{pct:5.1f}%] {done} updated, {errors} errors")

    conn.commit()
    print(f"\nDone. {done} spa_lin entries populated, {errors} errors.")
    conn.close()


if __name__ == "__main__":
    main()
