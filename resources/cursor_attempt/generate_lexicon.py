#!/usr/bin/env python3
"""
Generate GF lexicon files from WordNet symbols for use with RGL.

This script takes WordNet function symbols (e.g., dog_1_N, cat_1_N, chase_1_V2)
and generates abstract and concrete GF lexicon files that can be used with
the Grammatical Framework Resource Grammar Library (RGL) for translation.

The generated lexicons use RGL paradigm functions (mkN, mkV, mkV2, etc.) to
ensure proper morphological handling, and retrieve translations from WordNet
when available.
"""

import re
import os
import sys
import argparse
import pgf
from pathlib import Path
from typing import List, Tuple, Optional, Dict

# Default path to WordNet PGF file
DEFAULT_WORDNET_PGF = "WordNet.pgf"

# Mapping from GF Category to RGL Paradigm Function
# These functions handle morphological inflection automatically
CATEGORY_TO_RGL_PARADIGM = {
    "N": "mkN",
    "CN": "mkN",  # Common noun uses mkN
    "V": "mkV",
    "V2": "mkV2",
    "V3": "mkV3",
    "V2V": "mkV2V",
    "V2S": "mkV2S",
    "V2A": "mkV2A",
    "V2Q": "mkV2Q",
    "VS": "mkVS",
    "VQ": "mkVQ",
    "VA": "mkVA",
    "VV": "mkVV",
    "A": "mkA",
    "A2": "mkA2",
    "Adv": "mkAdv",
    "AdV": "mkAdV",
    "AdA": "mkAdA",
    "Card": "mkCard",
    "Ord": "mkOrd",
    "Prep": "mkPrep",
    "Pron": "mkPron",
    "Subj": "mkSubj",
    "Conj": "mkConj",
    "Det": "mkDet",
    "Quant": "mkQuant",
    "IQuant": "mkIQuant",
    "IDet": "mkIDet",
    "IP": "mkIP",
    "IAdv": "mkIAdv",
    "Interj": "mkInterj",
}

# Language code to WordNet language name mapping
LANG_CODE_TO_WORDNET = {
    "Eng": "WordNetEng",
    "Spa": "WordNetSpa",
    "Fre": "WordNetFre",
    "Ger": "WordNetGer",
    "Ita": "WordNetIta",
    "Por": "WordNetPor",
    "Rus": "WordNetRus",
    "Swe": "WordNetSwe",
    "Dan": "WordNetDan",
    "Nor": "WordNetNor",
    "Fin": "WordNetFin",
    "Est": "WordNetEst",
    "Pol": "WordNetPol",
    "Bul": "WordNetBul",
    "Ron": "WordNetRon",
    "Cze": "WordNetCze",
    "Slv": "WordNetSlv",
    "Jpn": "WordNetJpn",
    "Chi": "WordNetChi",
}


def load_wordnet_grammar(pgf_path: str = DEFAULT_WORDNET_PGF):
    """Load the WordNet PGF grammar file."""
    if not os.path.exists(pgf_path):
        raise FileNotFoundError(f"WordNet PGF file not found: {pgf_path}")
    return pgf.readPGF(pgf_path)


def extract_category_from_type(gf_type: str) -> str:
    """
    Extract the base category from a GF type string.
    
    Examples:
        "N" -> "N"
        "V2" -> "V2"
        "N -> S" -> "N"
        "(N -> S) -> S" -> "N"
    """
    # Remove function arrows and parentheses to get base category
    base_type = gf_type.split("->")[0].strip()
    base_type = base_type.strip("()")
    # Take the first word (category name)
    base_type = base_type.split()[0] if base_type.split() else base_type
    return base_type


def extract_base_word(func_name: str) -> str:
    """
    Extract the base word from a WordNet function name.
    
    Examples:
        "wn_dog_1_N" -> "dog"
        "dog_1_N" -> "dog"
        "paper_chase_N" -> "paper chase"
        "chase_1_V2" -> "chase"
    """
    # Remove 'wn_' prefix if present
    name = func_name[3:] if func_name.startswith("wn_") else func_name
    
    # Pattern: word_sense_Category or word_word_sense_Category
    # Match: word(s)_sense_number_Category
    match = re.match(r"(.+?)_\d+_[A-Z]", name)
    if match:
        base = match.group(1)
        return base.replace('_', ' ')
    
    # Fallback: try to extract before last underscore followed by category
    match = re.match(r"(.+?)_([A-Z][a-zA-Z]*)$", name)
    if match:
        base = match.group(1)
        return base.replace('_', ' ')
    
    # Last resort: return as-is with underscores replaced
    return name.replace('_', ' ')


def get_rgl_paradigm(gf_category: str) -> Optional[str]:
    """Get the RGL paradigm function for a given GF category."""
    return CATEGORY_TO_RGL_PARADIGM.get(gf_category)


def get_wordnet_linearization(grammar, func_name: str, lang_code: str) -> Optional[str]:
    """
    Get the linearized form of a WordNet function in a specific language.
    
    Args:
        grammar: The loaded PGF grammar
        func_name: Function name (e.g., "dog_1_N")
        lang_code: Language code (e.g., "Eng", "Fre", "Spa")
    
    Returns:
        Linearized word string, or None if language/function not available
    """
    wordnet_lang = LANG_CODE_TO_WORDNET.get(lang_code, f"WordNet{lang_code}")
    
    if wordnet_lang not in grammar.languages:
        return None
    
    try:
        expr = pgf.readExpr(func_name)
        lang = grammar.languages[wordnet_lang]
        linearized = lang.linearize(expr)
        return linearized
    except Exception as e:
        # Function might not exist in this language
        return None


def extract_function_info(grammar, function_list: Optional[List[str]] = None) -> List[Tuple[str, str, str, Optional[str]]]:
    """
    Extract function information from WordNet grammar.
    
    Args:
        grammar: The loaded PGF grammar
        function_list: Optional list of function names to extract.
                      If None, extracts all functions from WordNet.
    
    Returns:
        List of tuples: (func_name, gf_category, base_word, rgl_paradigm)
        - func_name: WordNet function name
        - gf_category: GF category (N, V2, etc.)
        - base_word: Base word form (English, extracted from function name)
        - rgl_paradigm: RGL paradigm function (mkN, mkV2, etc.) or None
    """
    results = []
    
    if function_list is None:
        functions_to_process = grammar.functions
    else:
        functions_to_process = [f for f in function_list if f in grammar.functions]
        missing = set(function_list) - set(functions_to_process)
        if missing:
            print(f"Warning: {len(missing)} functions not found in WordNet: {list(missing)[:10]}...")
    
    for func_name in functions_to_process:
        try:
            # Get the type from the grammar
            gf_type = grammar.functionType(func_name)
            gf_category = extract_category_from_type(str(gf_type))
            
            # Extract base word (English form as fallback)
            base_word = extract_base_word(func_name)
            
            # Get RGL paradigm function
            rgl_paradigm = get_rgl_paradigm(gf_category)
            
            if rgl_paradigm:
                results.append((func_name, gf_category, base_word, rgl_paradigm))
            else:
                print(f"Warning: No RGL paradigm mapping for category '{gf_category}' (function: {func_name})")
        except Exception as e:
            print(f"Warning: Error processing function {func_name}: {e}")
    
    return results


def generate_abstract_lexicon(function_data: List[Tuple[str, str, str, Optional[str]]], 
                             module_name: str = "WordNetLexicon",
                             base_module: str = "Grammar") -> str:
    """
    Generate the Abstract Lexicon file (WordNetLexicon.gf).
    
    Args:
        function_data: List of tuples (func_name, gf_category, base_word, rgl_paradigm)
        module_name: Name of the abstract module
        base_module: Base module to extend (default: "Grammar" - RGL base with categories)
    
    Returns:
        GF abstract syntax code as string
    """
    lines = [f"abstract {module_name} = {base_module} ** {{"]
    lines.append("  fun")
    
    for func_name, gf_category, _, _ in function_data:
        lines.append(f"    {func_name} : {gf_category} ;")
    
    lines.append("}")
    return "\n".join(lines) + "\n"


def generate_concrete_lexicon(function_data: List[Tuple[str, str, str, Optional[str]]],
                             lang_code: str,
                             abstract_module: str = "WordNetLexicon",
                             lang_module_prefix: str = "Lang",
                             grammar=None) -> str:
    """
    Generate a Concrete Lexicon file (e.g., WordNetEng.gf).
    
    Args:
        function_data: List of tuples (func_name, gf_category, base_word, rgl_paradigm)
        lang_code: Language code (e.g., "Eng", "Fre", "Spa")
        abstract_module: Name of the abstract module
        lang_module_prefix: Prefix for RGL language modules (default: "Lang" -> LangEng, LangFre)
        grammar: Optional PGF grammar to get WordNet linearizations
    
    Returns:
        GF concrete syntax code as string
    """
    concrete_module = f"{abstract_module}{lang_code}"
    rgl_lang_module = f"{lang_module_prefix}{lang_code}" if lang_module_prefix else lang_code
    rgl_resource = f"Res{lang_code}"
    paradigms_module = f"Paradigms{lang_code}"
    
    lines = [f"concrete {concrete_module} of {abstract_module} = {rgl_lang_module}, {paradigms_module} ** open {rgl_resource} in {{"]
    lines.append("  lin")
    
    missing_count = 0
    for func_name, _, base_word, rgl_paradigm in function_data:
        if not rgl_paradigm:
            continue
        
        # Try to get WordNet linearization for this language
        wordnet_word = None
        if grammar:
            wordnet_word = get_wordnet_linearization(grammar, func_name, lang_code)
        
        if wordnet_word:
            # Use WordNet's translation
            lines.append(f"    {func_name} = {rgl_paradigm} \"{wordnet_word}\" ;")
        else:
            # Language not available in WordNet - use English word with warning
            if grammar:
                missing_count += 1
                lines.append(f"    -- WARNING: {lang_code} translation not available, using English form")
            lines.append(f"    {func_name} = {rgl_paradigm} \"{base_word}\" ;")
    
    lines.append("}")
    
    if missing_count > 0 and grammar:
        # Add header comment about missing translations
        wordnet_lang = LANG_CODE_TO_WORDNET.get(lang_code, f"WordNet{lang_code}")
        if wordnet_lang not in grammar.languages:
            header = [
                f"-- WARNING: {lang_code} is not available in WordNet.pgf",
                f"-- {missing_count} words using English forms (may need manual translation)",
                f"-- Available languages: {', '.join(sorted(grammar.languages.keys()))}",
                ""
            ]
            return "\n".join(header + lines) + "\n"
    
    return "\n".join(lines) + "\n"


def main(function_list: Optional[List[str]] = None,
         output_dir: str = ".",
         languages: List[str] = None,
         wordnet_pgf_path: str = None,
         lang_module_prefix: str = "Lang",
         base_module: str = "Grammar",
         abstract_module_name: str = "WordNetLexicon",
         skip_missing_langs: bool = True):
    """
    Main function to generate GF lexicon files from WordNet.
    
    Args:
        function_list: Optional list of function names to include.
                      If None, includes all functions from WordNet.
        output_dir: Directory to write output files
        languages: List of language codes to generate concrete lexicons for
        wordnet_pgf_path: Path to WordNet PGF file
        lang_module_prefix: Prefix for RGL language modules (default: "Lang")
        base_module: Base abstract module to extend (default: "Grammar")
        abstract_module_name: Name for the abstract lexicon module
        skip_missing_langs: If True, skip languages not in WordNet
    """
    if languages is None:
        languages = ["Eng", "Fre"]
    
    if wordnet_pgf_path is None:
        wordnet_pgf_path = DEFAULT_WORDNET_PGF
    
    print("Loading WordNet grammar...")
    try:
        grammar = load_wordnet_grammar(wordnet_pgf_path)
        print(f"Loaded WordNet grammar with {len(grammar.functions)} functions")
        print(f"Available languages: {', '.join(sorted(grammar.languages.keys()))}")
    except Exception as e:
        print(f"Error loading WordNet grammar: {e}")
        return
    
    print("Extracting function information from WordNet...")
    function_data = extract_function_info(grammar, function_list)
    print(f"Extracted {len(function_data)} functions")
    
    if not function_data:
        print("No functions to process. Exiting.")
        return
    
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    # 1. Generate Abstract Lexicon
    print(f"Generating Abstract Lexicon ({abstract_module_name})...")
    abstract_content = generate_abstract_lexicon(function_data, 
                                                module_name=abstract_module_name,
                                                base_module=base_module)
    abstract_file_path = os.path.join(output_dir, f"{abstract_module_name}.gf")
    with open(abstract_file_path, "w", encoding="utf-8") as f:
        f.write(abstract_content)
    print(f"Generated: {abstract_file_path}")
    
    # 2. Generate Concrete Lexicons for each language
    for lang_code in languages:
        print(f"Generating {lang_code} Concrete Lexicon...")
        
        # Check if language is available in WordNet
        wordnet_lang = LANG_CODE_TO_WORDNET.get(lang_code, f"WordNet{lang_code}")
        if wordnet_lang not in grammar.languages:
            if skip_missing_langs:
                print(f"  Skipping {lang_code} (not available in WordNet)")
                print(f"  Available languages: {', '.join(sorted(grammar.languages.keys()))}")
                continue
            else:
                print(f"  Warning: {lang_code} not available in WordNet, generating with English words")
        
        concrete_content = generate_concrete_lexicon(function_data,
                                                    lang_code,
                                                    abstract_module=abstract_module_name,
                                                    lang_module_prefix=lang_module_prefix,
                                                    grammar=grammar)
        concrete_file_path = os.path.join(output_dir, f"{abstract_module_name}{lang_code}.gf")
        with open(concrete_file_path, "w", encoding="utf-8") as f:
            f.write(concrete_content)
        print(f"Generated: {concrete_file_path}")
    
    print("\nDone! Generated lexicon files can be compiled with GF and used with RGL for translation.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate GF lexicon files from WordNet symbols for use with RGL",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate lexicon for specific symbols:
  python generate_lexicon.py --symbols dog_1_N cat_1_N chase_1_V2
  
  # Generate lexicon from a file containing symbols (one per line):
  python generate_lexicon.py --file symbols.txt
  
  # Generate lexicon for all WordNet functions (very large!):
  python generate_lexicon.py --all
  
  # Specify output directory and languages:
  python generate_lexicon.py --symbols dog_1_N --output ./lexicons --languages Eng Fre Spa
  
  # Use Syntax module instead of Grammar (requires more RGL dependencies):
  python generate_lexicon.py --symbols dog_1_N --base-module Syntax
        """
    )
    
    parser.add_argument(
        "--symbols", "-s",
        nargs="+",
        help="List of WordNet function symbols to include (e.g., dog_1_N cat_1_N chase_1_V2)"
    )
    
    parser.add_argument(
        "--file", "-f",
        type=str,
        help="File containing function symbols (one per line)"
    )
    
    parser.add_argument(
        "--all", "-a",
        action="store_true",
        help="Include all functions from WordNet (generates very large lexicon!)"
    )
    
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=".",
        help="Output directory for generated GF files (default: current directory)"
    )
    
    parser.add_argument(
        "--languages", "-l",
        nargs="+",
        default=["Eng", "Fre"],
        help="Language codes for concrete lexicons (default: Eng Fre)"
    )
    
    parser.add_argument(
        "--wordnet-pgf",
        type=str,
        default=DEFAULT_WORDNET_PGF,
        help=f"Path to WordNet PGF file (default: {DEFAULT_WORDNET_PGF})"
    )
    
    parser.add_argument(
        "--base-module",
        type=str,
        default="Grammar",
        help="Base abstract module to extend (default: Grammar). Use 'Syntax' for full RGL syntax."
    )
    
    parser.add_argument(
        "--lang-prefix",
        type=str,
        default="Lang",
        help="Prefix for RGL language modules (default: Lang -> LangEng, LangFre)"
    )
    
    parser.add_argument(
        "--module-name",
        type=str,
        default="WordNetLexicon",
        help="Name for the abstract lexicon module (default: WordNetLexicon)"
    )
    
    parser.add_argument(
        "--allow-missing-langs",
        action="store_true",
        help="Generate lexicons for languages not in WordNet (will use English words)"
    )
    
    args = parser.parse_args()
    
    # Determine which functions to process
    function_list = None
    
    if args.all:
        function_list = None
        print("Warning: Processing all functions will generate a very large lexicon!")
    elif args.file:
        try:
            with open(args.file, 'r', encoding="utf-8") as f:
                function_list = [line.strip() for line in f if line.strip()]
            print(f"Loaded {len(function_list)} symbols from {args.file}")
        except FileNotFoundError:
            print(f"Error: File not found: {args.file}")
            sys.exit(1)
    elif args.symbols:
        function_list = args.symbols
    else:
        print("No symbols specified. Use --symbols, --file, or --all")
        print("Use --help for usage information")
        sys.exit(1)
    
    # Run main function
    main(function_list=function_list,
         output_dir=args.output,
         languages=args.languages,
         wordnet_pgf_path=args.wordnet_pgf,
         lang_module_prefix=args.lang_prefix,
         base_module=args.base_module,
         abstract_module_name=args.module_name,
         skip_missing_langs=not args.allow_missing_langs)


