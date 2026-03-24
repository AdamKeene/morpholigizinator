from pathlib import Path

from gensim.models import KeyedVectors

from .config import LANG_CONFIG, DEFAULT_GF_CAT

_ft_cache: dict = {}


def _load_ft_vectors(vectors_path):
    """Load fastText vectors, using a cached gensim binary for fast subsequent loads."""
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
    Expand keywords using fastText vectors.
    Returns dict {word: gf_category}; expanded words default to N.
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
            pass

    print(f"  {len(keywords)} keywords → {len(expanded)} after expansion")
    return expanded
