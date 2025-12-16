import nltk
import re
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.decomposition import LatentDirichletAllocation

# NLTK data (stopwords and wordnet) is assumed to be downloaded.

from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer

# --- Configuration ---
DOCUMENT_PATH = "/home/ubuntu/sample_document.txt"
N_TOPICS = 3  # Number of topics to extract
N_TOP_WORDS = 10 # Number of top words per topic

# --- Preprocessing Functions ---

def preprocess_text(text):
    """
    Tokenizes, removes punctuation, converts to lowercase, removes stopwords,
    and lemmatizes the text.
    """
    # Remove non-alphabetic characters and convert to lowercase
    text = re.sub(r'[^a-zA-Z\s]', '', text).lower()
    
    # Tokenize
    tokens = text.split()
    
    # Remove stopwords
    stop_words = set(stopwords.words('english'))
    tokens = [word for word in tokens if word not in stop_words]
    
    # Lemmatize
    lemmatizer = WordNetLemmatizer()
    tokens = [lemmatizer.lemmatize(word) for word in tokens]
    
    return " ".join(tokens)

def print_top_words(model, feature_names, n_top_words):
    """
    Helper function to print the top words for each topic.
    """
    for topic_idx, topic in enumerate(model.components_):
        message = f"Topic #{topic_idx + 1}: "
        message += " ".join([feature_names[i]
                             for i in topic.argsort()[:-n_top_words - 1:-1]])
        print(message)

# --- Main Execution ---

if __name__ == "__main__":
    print(f"Reading document from: {DOCUMENT_PATH}")
    try:
        with open(DOCUMENT_PATH, 'r') as f:
            document = f.read()
    except FileNotFoundError:
        print(f"Error: Document not found at {DOCUMENT_PATH}")
        exit()

    # 1. Preprocess the document
    print("Preprocessing text...")
    processed_document = preprocess_text(document)
    
    # LDA works best on a collection of documents, but we can treat the single
    # document as a collection of its own sentences or paragraphs. For simplicity,
    # we will use the whole document as a single text for now, but for better
    # topic separation, we should split it into paragraphs or sentences.
    # Let's split it into paragraphs for a slightly better result.
    texts = [p.strip() for p in document.split('\n\n') if p.strip()]
    processed_texts = [preprocess_text(t) for t in texts]
    
    if not processed_texts:
        print("Error: Document is empty or preprocessing resulted in no text.")
        exit()

    # 2. Create a Document-Term Matrix (DTM)
    print("Creating Document-Term Matrix...")
    # We use CountVectorizer to convert the text into a matrix of token counts
    # min_df=2 ensures we only consider words that appear in at least 2 "documents" (paragraphs)
    # max_df=0.95 removes words that appear in almost all "documents"
    vectorizer = CountVectorizer(min_df=1, max_df=0.95) # maybe no max_df?
    dtm = vectorizer.fit_transform(processed_texts)
    feature_names = vectorizer.get_feature_names_out()

    # 3. Apply Latent Dirichlet Allocation (LDA)
    print(f"Applying LDA with {N_TOPICS} topics...")
    lda = LatentDirichletAllocation(n_components=N_TOPICS, 
                                    random_state=42,
                                    max_iter=10,
                                    learning_method='online')
    lda.fit(dtm)

    # 4. Display the results
    print("\n--- Extracted Topics (Subject Matter) ---")
    print_top_words(lda, feature_names, N_TOP_WORDS)
    
    # For the next step, we'll need the top words from all topics.
    all_top_words = set()
    for topic in lda.components_:
        top_feature_indices = topic.argsort()[:-N_TOP_WORDS - 1:-1]
        for i in top_feature_indices:
            all_top_words.add(feature_names[i])
            
    print("\n--- Combined Subject Keywords for Next Step ---")
    print(sorted(list(all_top_words)))
    
    # Save the combined keywords to a file for the next phase
    with open("/home/ubuntu/subject_keywords.txt", "w") as f:
        f.write("\n".join(sorted(list(all_top_words))))
    print("\nKeywords saved to /home/ubuntu/subject_keywords.txt")
