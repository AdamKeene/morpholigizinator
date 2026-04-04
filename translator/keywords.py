import spacy
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.decomposition import LatentDirichletAllocation

from .config import LANG_CONFIG, SPACY_TO_GF, DEFAULT_GF_CAT

# ---------------------------------------------------------------------------
# Lexical aspect class tagging
#
# Stative verbs are the *last* to acquire perfective aspect marking (Aspect
# Hypothesis — Andersen & Shirai).  When a stative verb is in the keyword
# list, delay introducing preterite / simple-past patterns for it.
#
# These lists are intentionally small — only the highest-frequency statives
# that appear in GF WordNet across all supported languages.
# ---------------------------------------------------------------------------

_STATIVE_VERBS_EN = frozenset({
    "be", "have", "know", "like", "love", "hate", "want", "need",
    "seem", "appear", "contain", "belong", "own", "possess",
    "understand", "believe", "think", "remember", "forget",
})

_STATIVE_VERBS_ES = frozenset({
    "ser", "estar", "tener", "saber", "conocer", "querer", "necesitar",
    "gustar", "odiar", "amar", "parecer", "contener", "pertenecer",
    "poseer", "entender", "creer", "recordar", "olvidar",
})

_STATIVE_VERBS_DE = frozenset({
    "sein", "haben", "wissen", "kennen", "mögen", "lieben", "hassen",
    "wollen", "brauchen", "scheinen", "enthalten", "gehören", "besitzen",
    "verstehen", "glauben", "denken", "erinnern", "vergessen",
})

_STATIVE_VERBS_JA = frozenset({
    "ある", "いる", "できる", "知る", "好む", "嫌う", "思う",
    "必要", "属する", "持つ", "含む", "わかる", "信じる",
})

_STATIVE_BY_LANG = {
    "en": _STATIVE_VERBS_EN,
    "es": _STATIVE_VERBS_ES,
    "de": _STATIVE_VERBS_DE,
    "ja": _STATIVE_VERBS_JA,
}

# ---------------------------------------------------------------------------
# Grammar-accessibility weighting
#
# Some GF categories are harder to use in sentences at low levels.  The
# accessibility score (0.0 – 1.0) is combined with TF-IDF rank so that the
# lesson generator favours vocabulary that fits the learner's current grammar
# level.  Verbs are penalised slightly (require tense/agreement knowledge);
# adverbs and adjectives are rewarded (usable at level 1 as fragments).
# ---------------------------------------------------------------------------

_GF_CAT_ACCESSIBILITY = {
    "N":   1.0,    # always usable as NP fragment (A1)
    "A":   0.9,    # usable predicatively at A1 ("it is [adj]")
    "Adv": 0.85,   # bare adverb + simple clause (A1)
    "V":   0.7,    # needs tense/person (A2+)
    "V2":  0.65,   # needs tense/person + object (A2+)
}


def grammar_accessibility_weight(lemma: str, gf_cat: str, lang_code: str) -> float:
    """
    Return an accessibility weight (0.0 – 1.0) for this lemma+category pair.

    Stative verbs get an extra boost because they pair with simple present
    tense (the easiest structure) more naturally than dynamic verbs.

    This weight is intended to be multiplied with the raw TF-IDF / LDA score
    to produce a final priority score for vocabulary selection.
    """
    base = _GF_CAT_ACCESSIBILITY.get(gf_cat, 0.75)
    statives = _STATIVE_BY_LANG.get(lang_code, frozenset())
    if gf_cat in ("V", "V2") and lemma.lower() in statives:
        base = min(1.0, base + 0.15)
    return base


def is_stative(lemma: str, lang_code: str) -> bool:
    """Return True if the lemma is a known stative verb in lang_code."""
    return lemma.lower() in _STATIVE_BY_LANG.get(lang_code, frozenset())

# spaCy models are expensive to load — cache by language code
_nlp_cache: dict = {}


def _get_nlp(lang_code):
    if lang_code not in _nlp_cache:
        _nlp_cache[lang_code] = spacy.load(LANG_CONFIG[lang_code]["spacy_model"])
    return _nlp_cache[lang_code]


def _auto_topics(n_chunks: int, vocab_size: int) -> tuple[int, int]:
    """Heuristic: scale topic count with document size, capped at sane bounds."""
    n_topics = max(2, min(12, n_chunks // 15))
    n_words = max(5, min(20, vocab_size // (n_topics * 4)))
    return n_topics, n_words


def extract_keywords(chunks, lang_code, n_topics=None, n_words=None):
    """
    Run LDA topic modelling on text chunks and return domain keywords.

    Two passes over the text:
      1. spaCy tokenises each chunk, filters stop words / punctuation /
         digits, lemmatises tokens, and records their POS tags.
      2. TF-IDF vectorises the lemma sequences; LDA finds latent topics.
         The top n_words per topic become the keyword set.

    Returns
    -------
    keywords   : {lemma: gf_category}  — LDA top words (for expansion)
    all_content: {lemma: gf_category}  — every content word seen in the document

    all_content is passed to build_grammar() alongside keywords so that
    document-specific vocabulary not captured by LDA is still included in
    the compiled grammar.
    """
    print(f"1. Topic modelling on {lang_code.upper()} ({len(chunks)} chunks)...")

    nlp = _get_nlp(lang_code)
    cfg = LANG_CONFIG.get(lang_code, {})
    sym_filter = cfg.get("spacy_sym_filter", False)

    token_pos = {}  # {lemma: gf_cat} for all content words seen
    processed_chunks = []
    for chunk in chunks:
        doc = nlp(chunk)
        lemmas = []
        for t in doc:
            if t.is_punct or t.is_space or t.is_digit or t.is_stop:
                continue
            if sym_filter and t.pos_ == "SYM":
                continue
            lemma = t.lemma_.lower()
            if " " in lemma:
                # Some spaCy models include subject pronouns in verb lemmas
                # (e.g. Spanish "anima" → "animar él"). Skip multi-word lemmas —
                # they cannot be looked up in GF morphology or Wiktionary.
                continue
            token_pos[lemma] = SPACY_TO_GF.get(t.pos_, DEFAULT_GF_CAT)
            lemmas.append(lemma)
        if lemmas:
            processed_chunks.append(" ".join(lemmas))

    if not processed_chunks:
        print("  Warning: no meaningful tokens found.")
        return {}, {}

    if len(processed_chunks) == 1:
        # LDA requires multiple documents; with a single chunk just return all
        # content words as keywords and skip topic modelling entirely.
        print("  Single chunk — skipping LDA, using all content words as keywords.")
        return dict(token_pos), dict(token_pos)

    vectorizer = TfidfVectorizer(max_df=0.95, min_df=1, stop_words=None)
    dtm = vectorizer.fit_transform(processed_chunks)
    vocab_size = len(vectorizer.vocabulary_)

    auto_t, auto_w = _auto_topics(len(processed_chunks), vocab_size)
    resolved_topics = n_topics if n_topics is not None else auto_t
    resolved_words = n_words if n_words is not None else auto_w
    if n_topics is None or n_words is None:
        print(f"  Auto: {resolved_topics} topics × {resolved_words} words (vocab={vocab_size})")

    # LDA requires n_components ≤ n_samples (chunks)
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
