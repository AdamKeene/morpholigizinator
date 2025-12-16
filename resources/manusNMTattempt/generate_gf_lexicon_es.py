import os

# --- Configuration ---
INPUT_PATH = "/home/ubuntu/translated_lexicon_es.txt"
OUTPUT_PATH = "/home/ubuntu/ExpandedLexiconSpa.gf"
MODULE_NAME = "ExpandedLexiconSpa"

# --- Main Execution ---

if __name__ == "__main__":
    print(f"Reading translated lexicon from: {INPUT_PATH}")
    try:
        with open(INPUT_PATH, 'r') as f:
            # Each line is in the format: EN_WORD|GF_CAT|ES_WORD
            lexicon_data = [line.strip().split('|') for line in f if line.strip()]
    except FileNotFoundError:
        print(f"Error: Input lexicon file not found at {INPUT_PATH}")
        exit()

    if not lexicon_data:
        print("Error: Input lexicon file is empty or in the wrong format.")
        exit()

    print(f"Found {len(lexicon_data)} translated words.")

    # 1. Generate GF Lexicon Entries
    print("1. Generating GF lexicon entries for Spanish...")
    gf_entries = []
    # GF header
    gf_entries.append(f"concrete {MODULE_NAME} of Words = {{")
    gf_entries.append("  lincat")
    gf_entries.append("    CN = {{s : Str}}; -- Common Noun")
    gf_entries.append("  lin")

    # Generate an entry for each word
    for i, (en_word, gf_cat, es_word) in enumerate(lexicon_data):
        # Sanitize the English word to create a valid GF function name
        # (e.g., replace special characters, ensure it's a valid identifier)
        fun_name = ''.join(c for c in en_word.capitalize() if c.isalnum()) + f"_{i}"
        
        # Create the linearization rule for the Spanish word
        # This assumes a simple, uninflected noun. A real-world Spanish
        # grammar would require more complex handling for gender and number.
        # Example: lincat CN = {s : Gender -> Str; n : Number -> s G.g N.n}
        gf_entries.append(f"    {fun_name} : {gf_cat} = {{s = \"{es_word}\"}};")

    # GF footer
    gf_entries.append("}}")

    # 2. Save the GF Lexicon File
    with open(OUTPUT_PATH, "w") as f:
        f.write("\n".join(gf_entries))

    print(f"\n--- GF Lexicon Generation Complete ---")
    print(f"Spanish GF lexicon saved to {OUTPUT_PATH}")
