import os

# --- Configuration ---
LEXICON_PATH = "/home/ubuntu/expanded_lexicon.txt"
OUTPUT_GF_PATH = "/home/ubuntu/ExpandedLexicon.gf"
GF_CATEGORY = "CN"  # Common Noun
LEXICON_NAME = "ExpandedLexiconEng" # Name of the GF module

# --- Main Execution ---

if __name__ == "__main__":
    print(f"Reading expanded lexicon from: {LEXICON_PATH}")
    try:
        with open(LEXICON_PATH, 'r') as f:
            words = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        print(f"Error: Lexicon file not found at {LEXICON_PATH}")
        exit()

    if not words:
        print("Error: Lexicon file is empty.")
        exit()

    print(f"Found {len(words)} words to format into a GF lexicon.")

    # 2. Generate GF lexicon content
    gf_content = []
    gf_content.append(f"concrete {LEXICON_NAME} of Words = {{\n")
    gf_content.append(f"  lincat {GF_CATEGORY} = {{s : Str}};\n")
    gf_content.append(f"  lin")

    for i, word in enumerate(words):
        # Sanitize word for GF lin name (e.g., no hyphens)
        # For this simple case, we assume words are clean alpha strings
        gf_lin_name = word.capitalize() # A common convention
        
        # Format: l word_Word : CN = {s = "word"};
        entry = f"    {word}_{GF_CATEGORY} : {GF_CATEGORY} = {{s = \"{word}\"}}"
        gf_content.append(entry)
    
    gf_content.append("\n}}")

    # 3. Save the GF lexicon file
    with open(OUTPUT_GF_PATH, "w") as f:
        f.write("\n".join(gf_content))

    print(f"\n--- GF Lexicon Generation Complete ---")
    print(f"GF lexicon saved to {OUTPUT_GF_PATH}")
