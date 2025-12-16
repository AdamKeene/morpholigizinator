import os
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM, pipeline

# --- Configuration ---
INPUT_PATH = "/home/ubuntu/expanded_lexicon.txt"
OUTPUT_PATH = "/home/ubuntu/translated_lexicon_es.txt"
MODEL_NAME = "Helsinki-NLP/opus-mt-en-es"
TARGET_LANG = "es"
GF_CATEGORY = "CN" # Assuming Common Noun for all words

# --- Main Execution ---

if __name__ == "__main__":
    print(f"Reading English lexicon from: {INPUT_PATH}")
    try:
        with open(INPUT_PATH, 'r') as f:
            english_words = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        print(f"Error: Input lexicon file not found at {INPUT_PATH}")
        exit()

    if not english_words:
        print("Error: Input lexicon file is empty.")
        exit()

    print(f"Found {len(english_words)} English words.")

    # 1. Translation using MarianMT
    print(f"1. Translating {len(english_words)} words to {TARGET_LANG} using {MODEL_NAME}...")
    
    # Use the pipeline for easy batch translation
    try:
        # Download model and tokenizer if not already cached
        tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
        model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_NAME)
        translator = pipeline("translation", model=model, tokenizer=tokenizer)
        
        # Translate in batches
        translated_results = translator(english_words, batch_size=64)
        
        translated_words = [res['translation_text'] for res in translated_results]
        
    except Exception as e:
        print(f"An error occurred during NMT translation: {e}")
        # Fallback to a simple placeholder if translation fails
        translated_words = [f"TRANSLATION_FAILED_{word}" for word in english_words]

    # 2. Combine and Save
    print("2. Combining English word, GF category, and Spanish translation...")
    final_lexicon_entries = []
    
    for en_word, es_word in zip(english_words, translated_words):
        # Format: EN_WORD|GF_CAT|ES_WORD
        entry = f"{en_word}|{GF_CATEGORY}|{es_word}"
        final_lexicon_entries.append(entry)

    # Save the combined data to a file
    with open(OUTPUT_PATH, "w") as f:
        f.write("\n".join(final_lexicon_entries))

    print(f"\n--- Translation Complete ---")
    print(f"Combined lexicon data saved to {OUTPUT_PATH}")
