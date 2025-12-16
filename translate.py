import re
import pysrt
import spacy
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.decomposition import LatentDirichletAllocation
from nltk.corpus import wordnet as wn
# from nltk.corpus import omw

nlp = spacy.load('es_core_news_sm')

break_time = 15
N_TOPICS = 3
N_TOP_WORDS = 20

class File:
    def __init__(self, path):
        self.path = path
        self.subs = None
        self.text = None
        self.tokens = None
        self.vectorizer = None
        self.dtm = None
        self.feature_names = None
        self.lda = None
        self.topic_words = None
        self.translations = {}
        self.expanded_lexicon = {}

    def load_subs(self):
        encodings = ['utf-8', 'utf-8-sig', 'iso-8859-1', 'cp1252']
        subs = None
        for enc in encodings:
            try:
                subs = pysrt.open(self.path, encoding=enc)
                break
            except Exception:
                continue
        if subs is None:
            with open(self.path, 'rb') as fh:
                raw = fh.read()
            text = raw.decode('utf-8', errors='ignore')
            subs = pysrt.from_string(text)
        self.subs = subs

    def preprocess(self, break_sec=break_time, source_language='spanish'):
        """Parse an SRT using pysrt, normalize text, and split into documents by time gaps.

        Results are stored on the instance as `docs`.
        """
        if self.subs is None:
            self.load_subs()

        doc_strings = []
        doc_tokens = {}
        current_doc_string = []
        prev_end = 0.0

        for sub in self.subs:  # type: ignore
            start = sub.start.ordinal / 1000.0
            end = sub.end.ordinal / 1000.0


            text = sub.text.replace('\n', ' ').strip()
            text = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', text)

            doc = nlp(text)
            tokens = [t.lemma_.lower() for t in doc
                      if not t.is_stop and not t.is_punct and not t.is_space and getattr(t, 'is_alpha', True) and len(t.lemma_) > 1]

            if start > prev_end + break_sec and current_doc_string:
                doc_strings.append(' '.join(current_doc_string).strip())
                current_doc_string = []

            if tokens:
                current_doc_string.append(' '.join(tokens))
                for token in doc:
                    doc_tokens[token.lower_] = token # type: ignore

            prev_end = end

        if current_doc_string:
            doc_strings.append(' '.join(current_doc_string).strip())
        self.text = doc_strings
        self.tokens = doc_tokens

    def vectorize_and_fit_lda(self, n_topics=N_TOPICS, n_top_words=N_TOP_WORDS):
        if self.text is None:
            raise ValueError('Call `preprocess` before vectorizing')

        self.vectorizer = CountVectorizer(min_df=1, max_df=0.95)
        self.dtm = self.vectorizer.fit_transform(self.text)
        self.feature_names = self.vectorizer.get_feature_names_out()

        self.lda = LatentDirichletAllocation(n_components=n_topics,
                                             random_state=42,
                                             max_iter=10,
                                             learning_method='online')
        self.lda.fit(self.dtm)

        topic_words = set()
        for topic in self.lda.components_:
            top_feature_indices = topic.argsort()[:-n_top_words - 1:-1]
            for i in top_feature_indices:
                topic_words.add(self.feature_names[i])
        self.topic_words = topic_words

        # print topics for quick inspection
        for topic_idx, topic in enumerate(self.lda.components_):
            message = f"Topic #{topic_idx + 1}: "
            message += " ".join([self.feature_names[i] for i in topic.argsort()[:-n_top_words - 1:-1]]) # type: ignore
            print(message)

    def translate_topics(self, source_lang='spa', target_lang='eng'):
        if self.topic_words is None:
            raise ValueError('Call `vectorize_and_fit_lda` before translating')
        self.translations[target_lang] = get_context_aware_translation(self, source_lang=source_lang, target_lang=target_lang) # type: ignore
        print(self.translations[target_lang]) # type: ignore

def get_context_aware_translation(self, source_lang='spa', target_lang='eng'):
    """
    Translate topic words, preferring translations that co-occur semantically.
    Uses Open Multilingual Wordnet for local, fast lookup.
    """
    translations = {}
    synset_groups = {}
    topic_words = self.topic_words
    # Step 1: Get all possible translations for each word
    for word in topic_words:
        synsets = wn.synsets(word, lang=source_lang)
        if not synsets:
            translations[word] = [word]  # fallback: use original TODO don't
            synset_groups[word] = None
            print(f"no synsets found for '{word}'")
            continue
    
        # Collect all translation variants
        variants = set()
        for synset in synsets:
            for lemma in synset.lemmas(lang=target_lang): # type: ignore
                variants.add(lemma.name())
        
        translations[word] = list(variants) if variants else [word]
        synset_groups[word] = synsets
    
    # Step 2: Score translations by semantic coherence
    best_picks = {}
    for word in topic_words:
        if len(translations[word]) == 1:
            best_picks[word] = translations[word][0]
            continue
        
        # For each candidate translation, count semantic overlap
        scores = {}
        for candidate in translations[word]:
            score = 0
            candidate_synsets = wn.synsets(candidate, lang=target_lang)
            
            # Compare with other words' synsets in the topic
            for other_word in topic_words:
                if other_word == word:
                    continue
                word_synsets = synset_groups[other_word]
                if word_synsets is None:
                    continue
                for other_synset in word_synsets:
                    for cand_synset in candidate_synsets:
                        # Path similarity: 0-1, higher = more related
                        similarity = cand_synset.path_similarity(other_synset) # type: ignore
                        if similarity:
                            score += similarity
            
            scores[candidate] = score
        
        # Pick translation with highest coherence
        best_picks[word] = max(scores, key=lambda x: scores[x])
    
    return best_picks

if __name__ == "__main__":
    sample_path = 'resources/madagascar_srt/madagascar.srt'
    f = File(sample_path)
    f.preprocess()
    f.vectorize_and_fit_lda()
    f.translate_topics()

