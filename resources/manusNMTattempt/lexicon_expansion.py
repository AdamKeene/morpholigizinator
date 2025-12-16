import gensim.downloader as api
from gensim.models import KeyedVectors
import os

# --- Configuration ---
KEYWORDS_PATH = "/home/ubuntu/subject_keywords.txt"
OUTPUT_PATH = "/home/ubuntu/expanded_lexicon.txt"
MODEL_NAME = 'glove-wiki-gigaword-50'
TOP_N_SIMILAR = 20 # Number of similar words to find for each keyword

# --- Main Execution ---

if __name__ == "__main__":
    print(f"Loading word embedding model: {MODEL_NAME}...")
    
    # Check if the model is already downloaded and load it
    try:
        model_path = api.load(MODEL_NAME, return_path=True)
        model = KeyedVectors.load_word2vec_format(model_path, binary=False)
    except Exception as e:
        print(f"Error loading model: {e}")
        print("Please ensure the model is downloaded. Try running: python -c \"import gensim.downloader as api; api.load('glove-wiki-gigaword-50')\"")
        exit()

    print("Model loaded successfully.")

    # 1. Read keywords
    print(f"Reading keywords from: {KEYWORDS_PATH}")
    try:
        with open(KEYWORDS_PATH, 'r') as f:
            keywords = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        print(f"Error: Keywords file not found at {KEYWORDS_PATH}")
        exit()

    if not keywords:
        print("Error: Keywords file is empty.")
        exit()

    print(f"Found {len(keywords)} subject keywords.")

    # 2. Expand lexicon
    expanded_lexicon = set()
    
    for keyword in keywords:
        # Gensim models are case-sensitive, so we convert to lowercase
        # and check if the word is in the model's vocabulary
        lower_keyword = keyword.lower()
        
        if lower_keyword in model.key_to_index:
            try:
                # Find the top N most similar words
                similar_words = model.most_similar(lower_keyword, topn=TOP_N_SIMILAR)
                
                # Add the keyword itself and its similar words to the set
                expanded_lexicon.add(lower_keyword)
                for word, score in similar_words:
                    # Filter out non-alphabetic words (e.g., numbers, symbols)
                    if word.isalpha():
                        expanded_lexicon.add(word)
                        
                print(f"Expanded '{keyword}' with {len(similar_words)} related terms.")
            except KeyError:
                # This should not happen if we check key_to_index, but as a safeguard
                print(f"Warning: '{keyword}' not found in model vocabulary.")
        else:
            print(f"Warning: '{keyword}' not found in model vocabulary.")

    # 3. Save the expanded lexicon
    sorted_lexicon = sorted(list(expanded_lexicon))
    
    with open(OUTPUT_PATH, "w") as f:
        f.write("\n".join(sorted_lexicon))

    print(f"\n--- Lexicon Expansion Complete ---")
    print(f"Total unique words in expanded lexicon: {len(sorted_lexicon)}")
    print(f"Expanded lexicon saved to {OUTPUT_PATH}")
