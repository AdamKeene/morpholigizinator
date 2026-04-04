"""
Pre-populate the morphological form cache (resources/morph_cache.db).

Iterates every function in Parse.pgf for the requested languages, calls
tabularLinearize to extract the citation/dictionary form, and writes the
results to SQLite so that future lesson-generation calls skip the C library
for any word already in WordNet.

Building takes roughly 5–15 minutes per language depending on hardware.
The resulting DB (~50–150 MB) is loaded once per Python process and kept
in memory for sub-millisecond lookups.

Usage
-----
    python build_morph_cache.py                     # all LANG_CONFIG languages
    python build_morph_cache.py --langs de          # German only
    python build_morph_cache.py --langs de en       # German + English
    python build_morph_cache.py --pgf ./Parse.pgf   # custom grammar path

Output: resources/morph_cache.db
"""

import argparse
import re
import sys
import time

import pgf

from translator.config import LANG_CONFIG
from translator.morph_cache import write_db

PARSE_PGF = "./Parse.pgf"

_BRACKET_RE = re.compile(r'\[')

_V_INF_KEYS   = ('inf', 's (VInf False)', 's s (VInf False)', 'p')
_N_SG_KEYS    = ('s Sg Nom', 's Sg')
_A_PRED_KEY   = 's APred'

_CAT_SUFFIXES = {
    "N":   "_N",
    "V":   "_V",
    "V2":  "_V2",
    "A":   "_A",
    "Adv": "_Adv",
}


def _gf_cat(fn_name: str) -> str | None:
    for cat, suffix in _CAT_SUFFIXES.items():
        if fn_name.endswith(suffix):
            return cat
    return None


def _base_tree(fn_name: str, gf_cat: str) -> str:
    if gf_cat == "N":
        return f"UseN {fn_name}"
    if gf_cat == "V2":
        return f"SlashV2a {fn_name}"
    if gf_cat == "A":
        return f"PositA {fn_name}"
    return fn_name  # V, Adv


def _extract_form(table: dict, gf_cat: str) -> str | None:
    if gf_cat in ("V", "V2"):
        for key in _V_INF_KEYS:
            val = table.get(key, "")
            if val and not _BRACKET_RE.search(val):
                return val
    elif gf_cat == "N":
        for key in _N_SG_KEYS:
            val = table.get(key, "")
            if val and not _BRACKET_RE.search(val):
                return val
    elif gf_cat == "A":
        val = table.get(_A_PRED_KEY, "")
        if val and not _BRACKET_RE.search(val):
            return val
    return None


def build(pgf_path: str, lang_codes: list) -> None:
    print(f"Loading {pgf_path} ...")
    t0 = time.perf_counter()
    grammar = pgf.readPGF(pgf_path)
    print(f"  Loaded in {time.perf_counter()-t0:.1f}s  "
          f"({len(list(grammar.functions))} functions)")

    concretes = {}
    for lang in lang_codes:
        cfg = LANG_CONFIG.get(lang)
        if not cfg:
            print(f"  WARNING: '{lang}' not in LANG_CONFIG — skipping")
            continue
        suffix = cfg["gf_suffix"]
        name = f"Parse{suffix}"
        c = grammar.languages.get(name)
        if c is None:
            print(f"  WARNING: {name} not in {pgf_path} — skipping '{lang}'")
            continue
        concretes[lang] = c
        print(f"  Found {name}")

    if not concretes:
        sys.exit("No valid concretes — nothing to do.")

    entries = []
    fns = list(grammar.functions)
    total = len(fns)
    interval = max(1, total // 20)

    print(f"\nProcessing {total} functions × {len(concretes)} language(s)…")
    t0 = time.perf_counter()

    for i, fn_name in enumerate(fns):
        if i % interval == 0:
            pct = 100 * i // total
            elapsed = time.perf_counter() - t0
            print(f"  {pct:3d}%  {i}/{total}  ({elapsed:.0f}s elapsed)", end="\r")

        gf_cat = _gf_cat(fn_name)
        if gf_cat is None:
            continue  # PN, Conj, etc. — not vocabulary items we look up

        tree = _base_tree(fn_name, gf_cat)
        try:
            expr = pgf.readExpr(tree)
        except Exception:
            continue

        for lang, concrete in concretes.items():
            try:
                table = concrete.tabularLinearize(expr)
                surface = _extract_form(table, gf_cat)
                if not surface:
                    # Fall back to plain linearize
                    lin = concrete.linearize(expr)
                    if lin and not _BRACKET_RE.search(lin):
                        surface = lin
            except Exception:
                surface = None

            if surface:
                entries.append((fn_name, gf_cat, lang, surface))

    elapsed = time.perf_counter() - t0
    print(f"\n  Done in {elapsed:.0f}s — {len(entries):,} forms collected")

    print("Writing to morph_cache.db ...")
    n = write_db(entries)
    print(f"  {n:,} rows in DB")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build GF morphological form cache")
    parser.add_argument("--pgf",   default=PARSE_PGF,
                        help=f"Path to Parse.pgf (default: {PARSE_PGF})")
    parser.add_argument("--langs", nargs="+", default=list(LANG_CONFIG.keys()),
                        help="Language codes to include (default: all in LANG_CONFIG)")
    args = parser.parse_args()
    build(args.pgf, args.langs)
