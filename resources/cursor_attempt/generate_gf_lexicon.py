import re
import os
import sys
import argparse
import pgf
from pathlib import Path

# Path to WordNet PGF file
WORDNET_PGF_PATH = "WordNet.pgf"

# Mapping from GF Category to RGL Lexical Function
# This maps the base category (e.g., N, V, V2) to the RGL paradigm function
CATEGORY_TO_RGL = {
    "N": "mkN",
    "CN": "mkN",  # Common noun also uses mkN
    "V": "mkV",
    "V2": "mkV2",
    "V3": "mkV3",
    "A": "mkA",
    "Adv": "mkAdv",
    "Card": "mkCard",
    "AdA": "mkAdA",
    "AdV": "mkAdV",
    "Prep": "mkPrep",
    "Pron": "mkPron",
    # Add more mappings as needed
}

def load_wordnet_grammar(pgf_path=WORDNET_PGF_PATH):
    """Load the WordNet PGF grammar file."""
    if not os.path.exists(pgf_path):
        raise FileNotFoundError(f"WordNet PGF file not found: {pgf_path}")
    return pgf.readPGF(pgf_path)

def get_category_from_type(gf_type):
    """
    Extract the base category from a GF type string.
    e.g., "N" from "N", "V2" from "V2", "CN" from "CN"
    Handles complex types by taking the base category.
    """
    # GF types can be simple (N, V2) or complex (N -> S, etc.)
    # For lexicon generation, we typically want the base category
    # Remove function arrow types and parentheses
    base_type = gf_type.split("->")[0].strip()
    base_type = base_type.strip("()")
    return base_type

def extract_base_word(func_name):
    """
    Extracts the base word from a WordNet function name.
    Handles both patterns:
    - "wn_dog_1_N" -> "dog"
    - "dog_1_N" -> "dog"
    - "paper_chase_N" -> "paper chase"
    """
    # Remove 'wn_' prefix if present
    name = func_name[3:] if func_name.startswith("wn_") else func_name
    
    # Pattern: word_sense_Category or word_word_sense_Category
    # We want to extract everything before the last _\d+_Category pattern
    # Match pattern: word(s)_sense_number_Category
    match = re.match(r"(.+?)_\d+_[A-Z]", name)
    if match:
        base = match.group(1)
        return base.replace('_', ' ')
    
    # Fallback: try to extract before last underscore followed by category
    # This handles cases without sense numbers
    match = re.match(r"(.+?)_([A-Z][a-zA-Z]*)$", name)
    if match:
        base = match.group(1)
        return base.replace('_', ' ')
    
    # Last resort: return as-is with underscores replaced
    return name.replace('_', ' ')

def get_rgl_function(gf_category):
    """Get the RGL function for a given GF category."""
    return CATEGORY_TO_RGL.get(gf_category, None)

def get_wordnet_linearization(grammar, func_name, lang_code):
    """
    Get the linearized form of a WordNet function in a specific language.
    
    Args:
        grammar: The loaded PGF grammar
        func_name: Function name (e.g., "dog_1_N")
        lang_code: Language code (e.g., "Eng", "Fre", "Spa")
    
    Returns:
        Linearized word string, or None if language not available
    """
    # Map language codes to WordNet language names
    lang_map = {
        "Eng": "WordNetEng",
        "Spa": "WordNetSpa",
        "Fre": "WordNetFre",  # May not exist
    }
    
    wordnet_lang = lang_map.get(lang_code, f"WordNet{lang_code}")
    
    if wordnet_lang not in grammar.languages:
        return None
    
    try:
        expr = pgf.readExpr(func_name)
        lang = grammar.languages[wordnet_lang]
        return lang.linearize(expr)
    except Exception as e:
        return None

def extract_functions_from_wordnet(grammar, function_list=None):
    """
    Extract function information from WordNet grammar.
    
    Args:
        grammar: The loaded PGF grammar
        function_list: Optional list of function names to extract.
                      If None, extracts all functions from WordNet.
    
    Returns:
        List of tuples: (func_name, gf_category, base_word, rgl_func)
        base_word is the English form from function name extraction
    """
    results = []
    
    if function_list is None:
        # Extract all functions from WordNet
        functions_to_process = grammar.functions
    else:
        # Filter to only requested functions
        functions_to_process = [f for f in function_list if f in grammar.functions]
        missing = set(function_list) - set(functions_to_process)
        if missing:
            print(f"Warning: {len(missing)} functions not found in WordNet: {list(missing)[:10]}...")
    
    for func_name in functions_to_process:
        try:
            # Get the actual type from the grammar
            gf_type = grammar.functionType(func_name)
            gf_category = get_category_from_type(str(gf_type))
            
            # Extract base word (English form as fallback)
            base_word = extract_base_word(func_name)
            
            # Get RGL function
            rgl_func = get_rgl_function(gf_category)
            
            if rgl_func:
                results.append((func_name, gf_category, base_word, rgl_func))
            else:
                print(f"Warning: No RGL function mapping for category '{gf_category}' (function: {func_name})")
        except Exception as e:
            print(f"Warning: Error processing function {func_name}: {e}")
    
    return results

def generate_abstract_lexicon(function_data, module_name="WordNetLexicon", base_module="Grammar"):
    """
    Generates the Abstract Lexicon file (WordNetLexicon.gf).
    
    Args:
        function_data: List of tuples (func_name, gf_category, base_word, rgl_func)
        module_name: Name of the abstract module
        base_module: Base module to extend (default: Grammar - the RGL base module with categories)
                    Use "Syntax" for full RGL syntax, but this requires many dependencies
    """
    abstract_content = f"abstract {module_name} = {base_module} ** {{\n"
    abstract_content += "  fun\n"

    for func_name, gf_category, _, _ in function_data:
        abstract_content += f"    {func_name} : {gf_category} ;\n"

    abstract_content += "}\n"
    return abstract_content

def generate_concrete_lexicon(function_data, lang_code, abstract_module="WordNet", lang_module_prefix="Lang", grammar=None):
    """
    Generates a Concrete Lexicon file (e.g., WordNetEng.gf).
    
    Args:
        function_data: List of tuples (func_name, gf_category, base_word, rgl_func)
        lang_code: Language code (e.g., "Eng", "Fre")
        abstract_module: Name of the abstract module
        lang_module_prefix: Prefix for RGL language modules (default: "Lang" -> LangEng, LangFre)
                           Set to "" to use just the language code (Eng, Fre)
        grammar: Optional PGF grammar to get WordNet linearizations
    """
    # Determine module names based on language code
    concrete_module = f"{abstract_module}{lang_code}"
    # Use RGL language modules: LangEng, LangFre, etc.
    # These are the RGL concrete syntax modules that provide the language-specific grammar
    rgl_lang_module = f"{lang_module_prefix}{lang_code}" if lang_module_prefix else lang_code
    rgl_resource = f"Res{lang_code}"  # e.g., ResEng, ResFre (RGL resource modules)
    paradigms_module = f"Paradigms{lang_code}"  # e.g., ParadigmsEng, ParadigmsFre (RGL paradigm functions)

    concrete_content = f"concrete {concrete_module} of {abstract_module} = {rgl_lang_module}, {paradigms_module} ** open {rgl_resource} in {{\n"
    concrete_content += "  lin\n"

    missing_translations = []
    for func_name, _, base_word, rgl_func in function_data:
        if rgl_func:
            # Try to get WordNet linearization for this language
            if grammar:
                wordnet_word = get_wordnet_linearization(grammar, func_name, lang_code)
                if wordnet_word:
                    # Use WordNet's translation
                    concrete_content += f"    {func_name} = {rgl_func} \"{wordnet_word}\" ;\n"
                else:
                    # Language not available in WordNet - use English word with warning comment
                    concrete_content += f"    -- WARNING: {lang_code} translation not in WordNet, using English form\n"
                    concrete_content += f"    {func_name} = {rgl_func} \"{base_word}\" ;\n"
                    missing_translations.append(func_name)
            else:
                # No grammar provided, use base word
                concrete_content += f"    {func_name} = {rgl_func} \"{base_word}\" ;\n"

    concrete_content += "}\n"
    
    if missing_translations and grammar:
        # Check if language exists in WordNet
        lang_map = {"Eng": "WordNetEng", "Spa": "WordNetSpa", "Fre": "WordNetFre"}
        wordnet_lang = lang_map.get(lang_code, f"WordNet{lang_code}")
        if wordnet_lang not in grammar.languages:
            concrete_content = f"-- WARNING: {lang_code} is not available in WordNet.pgf\n"
            concrete_content += f"-- This lexicon will not compile correctly with RGL\n"
            concrete_content += f"-- Available languages: {list(grammar.languages.keys())}\n"
            concrete_content += f"-- Consider using a language that exists in WordNet or providing manual translations\n\n"
            concrete_content += f"concrete {concrete_module} of {abstract_module} = {rgl_lang_module}, {paradigms_module} ** open {rgl_resource} in {{\n"
            concrete_content += "  lin\n"
            for func_name, _, base_word, rgl_func in function_data:
                if rgl_func:
                    concrete_content += f"    {func_name} = {rgl_func} \"{base_word}\" ; -- English word, needs translation\n"
            concrete_content += "}\n"
    
    return concrete_content

# --- Main Execution ---

def main(function_list=None, output_dir=".", languages=["Eng", "Fre"], wordnet_pgf_path=None, lang_module_prefix="Lang", base_module="Grammar", skip_missing_langs=True):
    """
    Main function to generate GF lexicon files from WordNet.
    
    Args:
        function_list: Optional list of function names to include.
                      If None, includes all functions from WordNet.
        output_dir: Directory to write output files
        languages: List of language codes to generate concrete lexicons for
        wordnet_pgf_path: Path to WordNet PGF file (default: uses WORDNET_PGF_PATH)
        lang_module_prefix: Prefix for RGL language modules (default: "Lang")
        base_module: Base abstract module to extend (default: "Grammar" - the RGL base with categories)
    """
    if wordnet_pgf_path is None:
        wordnet_pgf_path = WORDNET_PGF_PATH
    
    print("Loading WordNet grammar...")
    try:
        grammar = load_wordnet_grammar(wordnet_pgf_path)
        print(f"Loaded WordNet grammar with {len(grammar.functions)} functions")
    except Exception as e:
        print(f"Error loading WordNet grammar: {e}")
        return
    
    print("Extracting function information from WordNet...")
    function_data = extract_functions_from_wordnet(grammar, function_list)
    print(f"Extracted {len(function_data)} functions")
    
    if not function_data:
        print("No functions to process. Exiting.")
        return
    
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    # 1. Generate Abstract Lexicon
    print("Generating Abstract Lexicon...")
    abstract_lexicon_content = generate_abstract_lexicon(function_data, base_module=base_module)
    abstract_file_path = os.path.join(output_dir, "WordNetLexicon.gf")
    with open(abstract_file_path, "w") as f:
        f.write(abstract_lexicon_content)
    print(f"Generated Abstract Lexicon: {abstract_file_path}")
    
    # 2. Generate Concrete Lexicons for each language
    for lang_code in languages:
        print(f"Generating {lang_code} Concrete Lexicon...")
        # Check if language is available in WordNet
        lang_map = {"Eng": "WordNetEng", "Spa": "WordNetSpa", "Fre": "WordNetFre"}
        wordnet_lang = lang_map.get(lang_code, f"WordNet{lang_code}")
        if wordnet_lang not in grammar.languages:
            if skip_missing_langs:
                print(f"  ERROR: {lang_code} not available in WordNet. Available: {list(grammar.languages.keys())}")
                print(f"  Skipping {lang_code} lexicon generation.")
                print(f"  To generate {lang_code}, you need to:")
                print(f"    1. Download WordNet with {lang_code} support, OR")
                print(f"    2. Manually create translations for each word")
                continue
            else:
                print(f"  Warning: {lang_code} not available in WordNet. Available: {list(grammar.languages.keys())}")
                print(f"  Generating with English words (will not compile correctly - needs manual translation)")
        
        concrete_content = generate_concrete_lexicon(function_data, lang_code, lang_module_prefix=lang_module_prefix, grammar=grammar)
        concrete_file_path = os.path.join(output_dir, f"WordNet{lang_code}.gf")
        with open(concrete_file_path, "w") as f:
            f.write(concrete_content)
        print(f"Generated {lang_code} Concrete Lexicon: {concrete_file_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate GF lexicon files from WordNet and RGL",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate lexicon for specific functions:
  python generate_gf_lexicon.py --functions dog_1_N cat_1_N chase_1_V2
  
  # Generate lexicon from a file containing function names (one per line):
  python generate_gf_lexicon.py --file symbols.txt
  
  # Generate lexicon for all WordNet functions (very large!):
  python generate_gf_lexicon.py --all
  
  # Specify output directory and languages:
  python generate_gf_lexicon.py --functions dog_1_N --output ./lexicons --languages Eng Fre Spa
        """
    )
    
    parser.add_argument(
        "--functions", "-f",
        nargs="+",
        help="List of WordNet function names to include (e.g., dog_1_N cat_1_N)"
    )
    
    parser.add_argument(
        "--file",
        type=str,
        help="File containing function names (one per line)"
    )
    
    parser.add_argument(
        "--all", "-a",
        action="store_true",
        help="Include all functions from WordNet (generates very large lexicon)"
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
        default=WORDNET_PGF_PATH,
        help=f"Path to WordNet PGF file (default: {WORDNET_PGF_PATH})"
    )
    
    parser.add_argument(
        "--base-module",
        type=str,
        default="Grammar",
        help="Base abstract module to extend (default: Grammar - the RGL base with categories). Use 'Syntax' for full RGL syntax (requires more dependencies)"
    )
    
    parser.add_argument(
        "--lang-prefix",
        type=str,
        default="Lang",
        help="Prefix for RGL language modules (default: Lang -> LangEng, LangFre). Set to empty string for no prefix."
    )
    
    parser.add_argument(
        "--allow-missing-langs",
        action="store_true",
        help="Generate lexicons for languages not in WordNet (will use English words and won't compile correctly)"
    )
    
    args = parser.parse_args()
    
    # Determine which functions to process
    function_list = None
    
    if args.all:
        function_list = None  # Process all functions
        print("Warning: Processing all functions will generate a very large lexicon!")
    elif args.file:
        # Read functions from file
        try:
            with open(args.file, 'r') as f:
                function_list = [line.strip() for line in f if line.strip()]
            print(f"Loaded {len(function_list)} functions from {args.file}")
        except FileNotFoundError:
            print(f"Error: File not found: {args.file}")
            sys.exit(1)
    elif args.functions:
        function_list = args.functions
    else:
        # Default: show help or use example functions for testing
        print("No functions specified. Use --functions, --file, or --all")
        print("Use --help for usage information")
        sys.exit(1)
    
    # Run main function
    main(function_list=function_list, output_dir=args.output, languages=args.languages, 
         wordnet_pgf_path=args.wordnet_pgf, lang_module_prefix=args.lang_prefix, base_module=args.base_module,
         skip_missing_langs=not args.allow_missing_langs)
