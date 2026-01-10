import nltk
import os
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM, pipeline

# --- Configuration ---
INPUT_PATH = "/home/ubuntu/expanded_lexicon.txt"
OUTPUT_PATH = "/home/ubuntu/translated_lexicon_with_pos_es.txt"
MODEL_NAME = "Helsinki-NLP/opus-mt-en-es"
TARGET_LANG = "es"

# Mapping from NLTK POS tags to simplified GF categories
# This is a simplification and would need refinement for a production GF grammar
POS_MAP = {
    'NN': 'CN',   # Noun, singular or mass -> Common Noun
    'NNS': 'CN',  # Noun, plural -> Common Noun
    'JJ': 'A',    # Adjective -> Adjective
    'JJR': 'A',   # Adjective, comparative -> Adjective
    'JJS': 'A',   # Adjective, superlative -> Adjective
    'VB': 'V',    # Verb, base form -> Verb
    'VBD': 'V',   # Verb, past tense -> Verb
    'VBG': 'V',   # Verb, gerund or present participle -> Verb
    'VBN': 'V',   # Verb, past participle -> Verb
    'VBP': 'V',   # Verb, non-3rd person singular present -> Verb
    'VBZ': 'V',   # Verb, 3rd person singular present -> Verb
    # Fallback for words that are not clearly N, V, or A
    'RB': 'Adv',  # Adverb -> Adverb
    'RBR': 'Adv', # Adverb, comparative -> Adverb
    'RBS': 'Adv', # Adverb, superlative -> Adverb
    'FW': 'CN',   # Foreign word (often proper nouns) -> Common Noun
    'CD': 'Num',  # Cardinal number -> Numeral
}

def get_gf_category(pos_tag):
    """Maps NLTK POS tag to a simplified GF category."""
    # Use the first two characters of the tag for generalization (e.g., NN, JJ, VB)
    return POS_MAP.get(pos_tag, 'CN') # Default to Common Noun if tag is unknown

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

    # 1. POS Tagging
    print("1. Performing POS Tagging on English words...")
    # NLTK's tagger expects a list of tokens
    # Explicitly load the tagger to avoid the resource lookup error
    # Load the pre-downloaded tagger model directly
    from nltk.data import find
    from nltk.tag.perceptron import PerceptronTagger
    tagger = PerceptronTagger()
    tagger.load(find('taggers/averaged_perceptron_tagger/averaged_perceptron_tagger.pickle'))
    tagged_words = tagger.tag(english_words)
    
    # Create a list of words to translate, prepended with a context word to help the NMT model
    # For single words, a simple context like "The word is [WORD]" can sometimes help.
    # However, for a lexicon, translating the word in isolation is often best, 
    # but we will use the POS tag to inform the GF category.
    words_to_translate = [word for word, tag in tagged_words]

    # 2. Translation using MarianMT
    print(f"2. Translating {len(words_to_translate)} words to {TARGET_LANG} using {MODEL_NAME}...")
    
    # Use the pipeline for easy batch translation
    try:
        translator = pipeline("translation", model=MODEL_NAME, tokenizer=MODEL_NAME)
        
        # Translate in batches (pipeline handles internal batching, but we can limit for safety)
        translated_results = translator(words_to_translate, batch_size=64)
        
        translated_words = [res['translation_text'] for res in translated_results]
        
    except Exception as e:
        print(f"An error occurred during NMT translation: {e}")
        exit()

    # 3. Combine and Save
    print("3. Combining English word, POS tag, GF category, and Spanish translation...")
    final_lexicon_entries = []
    
    for (en_word, en_tag), es_word in zip(tagged_words, translated_words):
        gf_cat = get_gf_category(en_tag)
        # Format: EN_WORD|EN_TAG|GF_CAT|ES_WORD
        entry = f"{en_word}|{en_tag}|{gf_cat}|{es_word}"
        final_lexicon_entries.append(entry)

    # Save the combined data to a file
    with open(OUTPUT_PATH, "w") as f:
        f.write("\n".join(final_lexicon_entries))

    print(f"\n--- POS Tagging and Translation Complete ---")
    print(f"Combined lexicon data saved to {OUTPUT_PATH}")
