import spacy
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.decomposition import LatentDirichletAllocation

from .config import LANG_CONFIG, SPACY_TO_GF, DEFAULT_GF_CAT

_nlp_cache: dict = {}


def _get_nlp(lang_code):
    if lang_code not in _nlp_cache:
        _nlp_cache[lang_code] = spacy.load(LANG_CONFIG[lang_code]["spacy_model"])
    return _nlp_cache[lang_code]


def _auto_topics(n_chunks: int, vocab_size: int) -> tuple[int, int]:
    n_topics = max(2, min(12, n_chunks // 15))
    n_words = max(5, min(20, vocab_size // (n_topics * 4)))
    return n_topics, n_words


def extract_keywords(chunks, lang_code, n_topics=None, n_words=None):
    """
    LDA topic modelling on text chunks.

    Returns:
        keywords   : {lemma: gf_category} for LDA top words
        all_content: {lemma: gf_category} for every content word seen
    """
    print(f"1. Topic modelling on {lang_code.upper()} ({len(chunks)} chunks)...")

    nlp = _get_nlp(lang_code)

    token_pos = {}
    processed_chunks = []
    for chunk in chunks:
        doc = nlp(chunk)
        lemmas = []
        for t in doc:
            if t.is_punct or t.is_space or t.is_digit or t.is_stop:
                continue
            if lang_code == "ja" and t.pos_ == "SYM":
                continue
            lemma = t.lemma_.lower()
            token_pos[lemma] = SPACY_TO_GF.get(t.pos_, DEFAULT_GF_CAT)
            lemmas.append(lemma)
        if lemmas:
            processed_chunks.append(" ".join(lemmas))

    if not processed_chunks:
        print("  Warning: no meaningful tokens found.")
        return {}, {}

    vectorizer = TfidfVectorizer(max_df=0.95, min_df=1, stop_words=None)
    dtm = vectorizer.fit_transform(processed_chunks)
    vocab_size = len(vectorizer.vocabulary_)

    auto_t, auto_w = _auto_topics(len(processed_chunks), vocab_size)
    resolved_topics = n_topics if n_topics is not None else auto_t
    resolved_words = n_words if n_words is not None else auto_w
    if n_topics is None or n_words is None:
        print(f"  Auto: {resolved_topics} topics × {resolved_words} words (vocab={vocab_size})")

    effective_topics = min(resolved_topics, dtm.shape[0])
    lda = LatentDirichletAllocation(n_components=effective_topics, random_state=42)
    lda.fit(dtm)

    feature_names = vectorizer.get_feature_names_out()
    keywords = {}
    for topic_idx, topic in enumerate(lda.components_):
        top_idx = topic.argsort()[:-resolved_words - 1:-1]
        top_words = [str(feature_names[i]) for i in top_idx]
        for w in top_words:
            keywords[w] = token_pos.get(w, DEFAULT_GF_CAT)
        print(f"  Topic {topic_idx}: {', '.join(top_words)}")

    return keywords, token_pos
