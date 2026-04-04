import sqlite3
from pathlib import Path

APERTIUM_DB = "./resources/apertium.db"


class ApertiumLookup:
    """
    Local Apertium bilingual dictionary for lemma-level word lookup.

    Role in the pipeline:
        Sits between Wiktionary and NMT. When a source-language word is not
        found by GF parsing or Wiktionary, Apertium translates it to English
        so the English form can be checked against ParseEng. If the English
        word parses, it is already in the WordNet grammar and needs no
        DomainLexicon entry.

    Populate the DB with build_apertium_db.py before use:
        python build_apertium_db.py

    Falls back gracefully (returns empty dict) when the DB is absent.
    """

    def __init__(self, db_path=APERTIUM_DB):
        self._db_path = db_path
        self._available = Path(db_path).exists()
        if not self._available:
            print(f"  Apertium DB not found at {db_path} — run build_apertium_db.py to populate.")

    def lookup_batch(self, words, source_lang, target_lang="en"):
        """
        Look up a list of source-language lemmas.
        Returns {source_lemma_lower: target_lemma} for found words only.

        The DB index is on lower(source_lemma), so case-insensitive matching is
        handled at the DB level without a full scan.
        """
        if not self._available or not words:
            return {}

        conn = sqlite3.connect(self._db_path)
        cur = conn.cursor()
        ph = ",".join("?" * len(words))
        cur.execute(
            f"SELECT source_lemma, target_lemma FROM mappings "
            f"WHERE source_lang=? AND target_lang=? AND lower(source_lemma) IN ({ph})",
            [source_lang, target_lang] + [w.lower() for w in words],
        )
        results = {row[0].lower(): row[1] for row in cur.fetchall()}
        conn.close()
        return results
