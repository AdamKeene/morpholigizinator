import sqlite3
from pathlib import Path

from .config import LANG_CONFIG
from .wordnet import _make_fun_name, _make_lin_expr

WIKTIONARY_DB = "./resources/wiktionary.db"

# Expected DB schema (populate from a Wiktionary dump):
#
#   CREATE TABLE translations (
#       source_lang  TEXT NOT NULL,
#       source_word  TEXT NOT NULL,
#       target_lang  TEXT NOT NULL,
#       target_word  TEXT NOT NULL,
#       PRIMARY KEY (source_lang, source_word, target_lang)
#   );
#   CREATE INDEX idx_lookup ON translations (source_lang, source_word);


class WiktionaryLookup:
    """
    Local Wiktionary bilingual dictionary for single-word lookup.

    Role in the pipeline:
        Sits between the WordNet surface index and Apertium. Wiktionary covers
        slang, regional vocabulary, neologisms, and proper nouns that GF WordNet
        does not include. It translates directly between the source language and
        all target languages without going through English.

    The DB is not yet populated — run a Wiktionary dump import script to fill it.
    Falls back gracefully (returns all words as remaining) when absent.
    """

    def __init__(self, db_path=WIKTIONARY_DB):
        self._db_path = db_path
        self._available = Path(db_path).exists()
        if not self._available:
            print(f"  Wiktionary DB not found at {db_path} — skipping.")

    def lookup_batch(self, words, source_lang, target_langs):
        """
        Look up a list of source-language words against all target_langs at once.
        Returns {source_word_lower: {target_lang: surface_form}}.
        """
        if not self._available or not words:
            return {}

        conn = sqlite3.connect(self._db_path)
        cur = conn.cursor()
        w_ph = ",".join("?" * len(words))
        l_ph = ",".join("?" * len(target_langs))
        cur.execute(
            f"SELECT source_word, target_lang, target_word FROM translations "
            f"WHERE source_lang=? AND lower(source_word) IN ({w_ph}) AND target_lang IN ({l_ph})",
            [source_lang] + [w.lower() for w in words] + list(target_langs),
        )
        results = {}
        for src_word, tgt_lang, tgt_word in cur.fetchall():
            results.setdefault(src_word.lower(), {})[tgt_lang] = tgt_word
        conn.close()
        return results

    def build_entries(self, words_cats, source_lang, target_langs):
        """
        Look up words_cats ({source_word: gf_cat}) in Wiktionary, build GF
        entry dicts for hits, and return the remaining unresolved words.

        Returns (wikt_entries, remaining_words_cats).

        fun_name is keyed on the English translation when available (for
        consistency with WordNet fun_names), falling back to the source word.

        The source word itself is always included as the source_lang lin so
        the GF concrete for the source language has a valid linearisation.
        This avoids needing a redundant (source_lang, word, source_lang, word)
        row in the DB.
        """
        if not self._available or not words_cats:
            return [], dict(words_cats)

        hits = self.lookup_batch(list(words_cats.keys()), source_lang, target_langs)
        entries, remaining = [], {}

        for src_w, cat in words_cats.items():
            lang_surfaces = hits.get(src_w.lower())
            if lang_surfaces:
                lins = {
                    lang: _make_lin_expr(surface, cat, lang)
                    for lang, surface in lang_surfaces.items()
                    if lang in LANG_CONFIG
                }
                # Always include the source word as the source-language lin.
                # The DB stores target translations; the source surface is the
                # word we looked up, which we already have.
                if source_lang not in lins:
                    lins[source_lang] = _make_lin_expr(src_w, cat, source_lang)
                fun_name = _make_fun_name(lang_surfaces.get("en", src_w), cat)
                entries.append({
                    "fun_name": fun_name,
                    "category": cat,
                    "src_word": lang_surfaces.get("en", src_w),
                    "lins": lins,
                })
            else:
                remaining[src_w] = cat

        return entries, remaining
