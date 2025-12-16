#!/usr/bin/env python3
"""
Minimal helper for peeking into WordNet.pgf so we know what information is
available before wiring the full lexicon generator.

Given one or more WordNet function symbols (e.g. dog_1_N) it prints:
  • the GF type/category (needed to choose the correct RGL paradigm such as mkN)
  • the base English form inferred from the symbol name (fallback lexeme)
  • the linearizations that already exist inside WordNet for each requested language
"""

from __future__ import annotations

import argparse
import os
import pgf
import re
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional

DEFAULT_WORDNET_PGF = "WordNet.pgf"


@dataclass
class SymbolRecord:
    name: str
    category: str
    base_form: str
    linearizations: Dict[str, Optional[str]]


def load_wordnet(path: str) -> pgf.PGF:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Cannot find WordNet PGF at {path}")
    return pgf.readPGF(path)


def extract_category(func_type: str) -> str:
    base = func_type.split("->")[0].strip()
    return base.strip("()")


def extract_base_form(func_name: str) -> str:
    name = func_name[3:] if func_name.startswith("wn_") else func_name
    match = re.match(r"(.+?)_\\d+_[A-Z]", name)
    if match:
        return match.group(1).replace("_", " ")
    match = re.match(r"(.+?)_[A-Z][a-zA-Z]*$", name)
    if match:
        return match.group(1).replace("_", " ")
    return name.replace("_", " ")


def linearize_symbol(grammar: pgf.PGF, symbol: str, wordnet_lang: str) -> Optional[str]:
    if wordnet_lang not in grammar.languages:
        return None
    try:
        expr = pgf.readExpr(symbol)
        return grammar.languages[wordnet_lang].linearize(expr)
    except Exception:
        return None


def inspect_symbols(
    grammar: pgf.PGF, symbols: List[str], lang_codes: List[str]
) -> List[SymbolRecord]:
    records: List[SymbolRecord] = []
    lang_map = {code: f"WordNet{code}" for code in lang_codes}

    for symbol in symbols:
        if symbol not in grammar.functions:
            print(f"Warning: {symbol} not found in WordNet.pgf")
            continue

        gf_type = str(grammar.functionType(symbol))
        category = extract_category(gf_type)
        base_form = extract_base_form(symbol)
        linearizations = {}

        for code, lang_name in lang_map.items():
            linearizations[code] = linearize_symbol(grammar, symbol, lang_name)

        records.append(
            SymbolRecord(
                name=symbol,
                category=category,
                base_form=base_form,
                linearizations=linearizations,
            )
        )

    return records


def main():
    parser = argparse.ArgumentParser(
        description="Inspect WordNet symbols and preview the data needed for lexicon generation.",
    )
    parser.add_argument(
        "symbols",
        nargs="+",
        help="WordNet symbols such as dog_1_N cat_1_N chase_1_V2",
    )
    parser.add_argument(
        "--wordnet",
        default=DEFAULT_WORDNET_PGF,
        help=f"Path to WordNet.pgf (default: {DEFAULT_WORDNET_PGF})",
    )
    parser.add_argument(
        "--languages",
        "-l",
        nargs="+",
        default=["Eng"],
        help="Language codes to query inside WordNet (default: Eng).",
    )
    args = parser.parse_args()

    grammar = load_wordnet(args.wordnet)
    print(f"Loaded WordNet grammar with {len(grammar.functions)} functions")
    print("WordNet languages available:", ", ".join(sorted(grammar.languages.keys())))

    records = inspect_symbols(grammar, args.symbols, args.languages)
    if not records:
        return

    for record in records:
        print("-" * 40)
        print(f"Symbol      : {record.name}")
        print(f"Category    : {record.category}")
        print(f"Base form   : {record.base_form}")
        for code, lin in record.linearizations.items():
            print(f"  {code:<5} -> {lin or '[missing]'}")


if __name__ == "__main__":
    main()

