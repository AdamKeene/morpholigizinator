from pathlib import Path

from gensim.models import KeyedVectors

from .config import LANG_CONFIG, DEFAULT_GF_CAT

# Process-level cache so vectors are only loaded once per session
_ft_cache: dict = {}


def _load_ft_vectors(vectors_path):
    """
    Load fastText vectors, using a gensim binary cache for fast subsequent loads.

    fastText .vec files (text format) take ~30s to parse for 200k words. On
    first load the vectors are converted and saved as a .gensim binary next to
    the .vec file; subsequent loads use KeyedVectors.load() which is much
    faster (~1–2s via mmap).
    """
    if vectors_path in _ft_cache:
        return _ft_cache[vectors_path]

    cache_path = vectors_path + ".gensim"
    if Path(cache_path).exists():
        ft = KeyedVectors.load(cache_path, mmap="r")
    else:
        print(f"  Converting {Path(vectors_path).name} to gensim format (one-time)...")
        ft = KeyedVectors.load_word2vec_format(vectors_path, binary=False, limit=200000)
        ft.save(cache_path)

    _ft_cache[vectors_path] = ft
    return ft


def semantic_expansion(keywords, lang_code, top_n):
    """
    Expand the LDA keyword set using fastText nearest-neighbour vectors.

    For each keyword, find the top_n most similar words in the fastText space
    and add them to the vocabulary. This captures morphological variants,
    synonyms, and related domain terms that LDA may not have surfaced as
    top words but are still relevant to the document's subject matter.

    Only alphabetic words longer than 2 characters are added — this filters
    out punctuation artefacts and single-letter tokens from the vector space.

    Expanded words are assigned DEFAULT_GF_CAT (N) since POS context is
    unavailable for similarity-derived neighbours.

    Returns {word: gf_category} including both original keywords and additions.
    """
    vectors_path = LANG_CONFIG[lang_code]["fasttext_vec"]
    print(f"2. Expanding with fastText vectors for {lang_code.upper()}...")

    try:
        ft = _load_ft_vectors(vectors_path)
    except Exception as e:
        print(f"  Could not load fastText model: {e}")
        return dict(keywords)

    expanded = dict(keywords)
    for word in list(keywords):
        try:
            for similar, _ in ft.most_similar(word, topn=top_n):
                if len(similar) > 2 and similar.isalpha() and similar not in expanded:
                    expanded[similar] = DEFAULT_GF_CAT
        except KeyError:
            pass  # word not in fastText vocabulary — skip silently

    print(f"  {len(keywords)} keywords → {len(expanded)} after expansion")
    return expanded
