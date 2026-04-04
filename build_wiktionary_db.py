"""
Build the Wiktionary lookup DB from kaikki.org pre-parsed Wiktionary data.

For each source language, downloads the JSONL from kaikki.org (which is the
English Wiktionary parsed into one JSON object per line), extracts an English
equivalent from each entry's first usable gloss, and stores it in the DB.

Result: (source_lang, source_word) → English equivalent that can be used to
find the right GF WordNet entry without NMT.

Coverage complement:
    OMW covers ~30-57k synsets per language (standard vocabulary).
    This covers everything in English Wiktionary: slang, neologisms, proper
    nouns, regional terms, loan words — whatever OMW misses.

Run once:
    python build_wiktionary_db.py

Re-run to add a new language:
    python build_wiktionary_db.py --lang ja

Disk space: ~300-900 MB download per language, ~50-150 MB resulting SQLite DB.
"""

import argparse
import json
import re
import sqlite3
import sys
import urllib.request
from pathlib import Path

WIKTIONARY_DB = "./resources/wiktionary.db"

KAIKKI_URLS = {
    "es": "https://kaikki.org/dictionary/Spanish/kaikki.org-dictionary-Spanish.jsonl",
    "de": "https://kaikki.org/dictionary/German/kaikki.org-dictionary-German.jsonl",
    "ja": "https://kaikki.org/dictionary/Japanese/kaikki.org-dictionary-Japanese.jsonl",
}

# Only index these POS types — others (pronoun, conjunction, prep, etc.)
# rarely appear as content words in our source documents.
VALID_POS = {"noun", "verb", "adj", "adv", "name"}

# Gloss prefixes that indicate an inflection form rather than a definition.
# These entries don't have a usable English equivalent — skip them.
_INFLECTION_PREFIXES = (
    "inflection of", "plural of", "form of", "alternative form of",
    "alternative spelling of", "past tense of", "comparative of",
    "superlative of", "feminine of", "masculine of", "diminutive of",
    "augmentative of", "gerund of", "participle of", "misspelling of",
    "eye dialect of", "obsolete spelling of", "archaic form of",
    "nonstandard form of", "synonym of", "abbreviation of",
    # Verb conjugation form entries — the "gloss" is a grammatical description,
    # not a translation. Spanish verbs in English Wiktionary often appear as
    # their conjugated forms (e.g., "fa" = second-person singular imperative of far).
    "first-person singular", "second-person singular", "third-person singular",
    "first-person plural", "second-person plural", "third-person plural",
    "first person singular", "second person singular", "third person singular",
)


_STOPWORDS = frozenset({"of", "the", "a", "an", "in", "at", "to", "and", "or", "for"})


def _extract_english(gloss: str) -> str | None:
    """
    Extract a clean English equivalent from a Wiktionary gloss string.

    Glosses look like:
        "truck (Mexican slang)"          → "truck"
        "foot (a part of the body)"     → "foot"
        "free, without charge"          → "free"
        "to absorb"                     → "absorb"  (strips "to" prefix)
        "inflection of correr"          → None  (skip)
        "the act of running quickly"    → None  (too long)

    Returns None if no clean single-word/short-phrase equivalent can be found.
    """
    gloss = gloss.strip()
    if not gloss:
        return None
    if gloss.lower().startswith(_INFLECTION_PREFIXES):
        return None

    # Take everything before the first comma, parenthesis, period, or semicolon
    m = re.match(r"^([^,(;.]+)", gloss)
    if not m:
        return None
    result = m.group(1).strip().lower()

    # Strip the infinitive "to " prefix common in verb glosses
    if result.startswith("to "):
        result = result[3:].strip()

    # Reject phrases longer than 3 words (it's a definition, not a lemma)
    if len(result.split()) > 3:
        return None

    # Reject if it contains characters that aren't letters, spaces, or hyphens
    if re.search(r"[^a-z\s\-]", result):
        return None

    # Reject bare function words — these are never useful as WordNet keys
    if result in _STOPWORDS:
        return None

    return result or None


def _create_db(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS translations (
            source_lang  TEXT NOT NULL,
            source_word  TEXT NOT NULL,
            target_lang  TEXT NOT NULL,
            target_word  TEXT NOT NULL,
            PRIMARY KEY (source_lang, source_word, target_lang)
        );
        CREATE INDEX IF NOT EXISTS idx_lookup
            ON translations (source_lang, source_word);
    """)
    conn.commit()


def build_lang(lang: str, conn: sqlite3.Connection, commit_every: int = 5000):
    url = KAIKKI_URLS.get(lang)
    if not url:
        print(f"No kaikki.org URL configured for language '{lang}'")
        return

    print(f"\n[{lang}] Downloading {url}")
    print("  (this is a large file — may take several minutes)")

    cur = conn.cursor()
    inserted = skipped = total = 0

    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as response:
        buffer = ""
        while True:
            chunk = response.read(65536).decode("utf-8", errors="replace")
            if not chunk:
                break
            buffer += chunk
            lines = buffer.split("\n")
            buffer = lines[-1]  # last line may be incomplete — keep for next chunk

            for line in lines[:-1]:
                line = line.strip()
                if not line:
                    continue
                total += 1
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    skipped += 1
                    continue

                word = obj.get("word", "").strip()
                pos = obj.get("pos", "")

                if not word or pos not in VALID_POS:
                    skipped += 1
                    continue

                # Skip words that look like phrases, numbers, or symbols
                if len(word) > 60 or any(c.isdigit() for c in word):
                    skipped += 1
                    continue

                # Find first usable English gloss across all senses
                english = None
                for sense in obj.get("senses", []):
                    for gloss in sense.get("glosses", []):
                        english = _extract_english(gloss)
                        if english:
                            break
                    if english:
                        break

                if not english:
                    skipped += 1
                    continue

                # Store: source_word → English equivalent.
                # The source-language lin is the source word itself and is
                # added by WiktionaryLookup.build_entries() at runtime,
                # so we don't need a redundant (lang, word, lang, word) row.
                cur.execute(
                    "INSERT OR IGNORE INTO translations VALUES (?,?,?,?)",
                    (lang, word.lower(), "en", english),
                )
                inserted += 1

                if inserted % commit_every == 0:
                    conn.commit()
                    pct = (inserted + skipped) / max(total, 1) * 100
                    print(f"  {inserted:,} inserted, {skipped:,} skipped ({pct:.0f}% of lines processed)")

        # Process any remaining buffered content
        if buffer.strip():
            try:
                obj = json.loads(buffer)
                word = obj.get("word", "").strip()
                pos = obj.get("pos", "")
                if word and pos in VALID_POS and not any(c.isdigit() for c in word):
                    for sense in obj.get("senses", []):
                        for gloss in sense.get("glosses", []):
                            english = _extract_english(gloss)
                            if english:
                                cur.execute(
                                    "INSERT OR IGNORE INTO translations VALUES (?,?,?,?)",
                                    (lang, word.lower(), "en", english),
                                )
                                inserted += 1
                                break
                        else:
                            continue
                        break
            except Exception:
                pass

        conn.commit()

    cur.execute(
        "SELECT COUNT(*) FROM translations WHERE source_lang=?", (lang,)
    )
    final_count = cur.fetchone()[0]
    print(f"[{lang}] Done: {inserted:,} entries inserted, {skipped:,} skipped")
    print(f"[{lang}] Total rows in DB for this language: {final_count:,}")


def main():
    parser = argparse.ArgumentParser(description="Build Wiktionary lookup DB from kaikki.org data")
    parser.add_argument(
        "--lang", nargs="+", default=list(KAIKKI_URLS.keys()),
        choices=list(KAIKKI_URLS.keys()),
        help="Languages to process (default: all configured languages)",
    )
    parser.add_argument(
        "--db", default=WIKTIONARY_DB,
        help=f"Output SQLite DB path (default: {WIKTIONARY_DB})",
    )
    args = parser.parse_args()

    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(args.db)
    _create_db(conn)

    for lang in args.lang:
        build_lang(lang, conn)

    conn.close()
    size_mb = Path(args.db).stat().st_size / 1e6
    print(f"\nWiktionary DB ready at {args.db} ({size_mb:.0f} MB)")


if __name__ == "__main__":
    main()
