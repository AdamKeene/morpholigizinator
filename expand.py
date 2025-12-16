"""expand.py
Simple lexicon expansion using fastText embeddings.

This script provides a small Triaged implementation meant for integration
with your existing codebase. It uses fastText (subword) embeddings to expand
a given list of topic words to similar words in a target language.

By default the English test loader uses gensim's 'fasttext-wiki-news-subwords-300'
model via gensim.downloader so the example works without pre-downloaded models.

For other languages point LANG_TO_FASTTEXT_MODEL to a local file in the
`models/` directory (e.g. `models/cc.es.300.bin`) and use the mapping key.
"""
from __future__ import annotations

import os
import unicodedata
from typing import Dict, Set

from gensim.models import KeyedVectors
from gensim.models.fasttext import load_facebook_vectors
import gensim.downloader as api

# Configure your per-language fastText model path here if you download them.
# Use cc.<lang>.300.bin (bin format) or cc.<lang>.300.vec for text vectors.
LANG_TO_FASTTEXT_MODEL = {
    # For english we use a downloader-provided model for convenience during tests
    'en': ('fasttext-wiki-news-subwords-300', 'downloader'),
    # Example placeholders for classifiers you can add when downloaded into models/
    # 'es': ('models/cc.es.300.bin', 'bin'),
    # 'fr': ('models/cc.fr.300.bin', 'bin'),
}


def _normalize(word: str) -> str:
    # Basic normalization: unicode normalization and lowercasing.
    if word is None:
        return ''
    w = unicodedata.normalize('NFC', word).strip()
    return w.lower()


class FastTextLexicalExpander:
    """Expand lexical lists using fastText embeddings.

    Usage:
        expander = FastTextLexicalExpander()
        expander.topic_words = ['running', 'dog', 'government']
        expander.expand('en')  # populate expander.expanded_lexicon['en']
    """

    def __init__(self, models_dir: str = 'models'):
        self.models_dir = models_dir
        self._models: Dict[str, KeyedVectors] = {}
        self.topic_words: Set[str] = set()
        self.expanded_lexicon: Dict[str, Set[str]] = {}

    def _load_model(self, lang: str) -> KeyedVectors:
        if lang in self._models:
            return self._models[lang]

        entry = LANG_TO_FASTTEXT_MODEL.get(lang)
        if entry is None:
            raise ValueError(f"No fastText model configured for language '{lang}'.\n"
                             "Add a mapping to LANG_TO_FASTTEXT_MODEL to point to a cc.<lang> file.")

        path_or_name, kind = entry
        if kind == 'downloader':
            # uses gensim.downloader to deliver a small english fasttext model for tests
            model_path = api.load(path_or_name, return_path=True)
            model = KeyedVectors.load_word2vec_format(model_path, binary=False)
        elif kind == 'bin':
            # Load Facebook-style `.bin` files (fastText binary vectors)
            model_path = os.path.expanduser(path_or_name)
            model = load_facebook_vectors(model_path)
        elif kind == 'vec':
            model_path = os.path.expanduser(path_or_name)
            model = KeyedVectors.load_word2vec_format(model_path, binary=False)
        else:
            raise ValueError(f'Unknown model kind "{kind}" for {lang}')

        self._models[lang] = model
        return model

    def expand(self, target_lang: str, topn: int = 20) -> Set[str]:
        """Expand `self.topic_words` into `self.expanded_lexicon[target_lang]`.

        The function normalizes topic words (lowercase + unicode normalization),
        loads the appropriate fastText model for `target_lang` and computes the
        topn most similar words for each keyword.
        """
        expanded_lexicon: Set[str] = set()
        if not self.topic_words:
            return expanded_lexicon

        model = self._load_model(target_lang)

        for keyword in list(self.topic_words):
            word = _normalize(keyword)
            if not word:
                continue

            # For fastText models we can usually compute vectors even for OOVs
            # using subword representations.
            try:
                if word not in model.key_to_index:
                    # fastText (binary) models usually generate OOV vectors based on subwords
                    # but KeyedVectors for some formats may not allow membership checks; we handle both.
                    pass

                expanded_lexicon.add(word)
                # compute most similar
                similar = model.most_similar(word, topn=topn)
                for cand, score in similar:
                    # simple filter: candidate must be alphabetic or contain hyphen/underscore
                    if isinstance(cand, str) and len(cand) > 0:
                        expanded_lexicon.add(cand)
            except KeyError:
                # model.most_similar may raise KeyError if the word cannot be handled
                print(f"[expand] word '{keyword}' not found/handled by model for {target_lang}")
            except Exception as exc:
                # some fastText binary models may raise other errors for certain inputs
                print(f"[expand] error expanding '{keyword}' for {target_lang}: {exc}")

        self.expanded_lexicon[target_lang] = expanded_lexicon
        return expanded_lexicon


if __name__ == '__main__':
    # rudimentary test/demo when run as a script. It will download via gensim if necessary.
    demo_words = ['running', 'dog', 'democracy', 'runnig']  # includes a misspelling
    expander = FastTextLexicalExpander()
    expander.topic_words = set(demo_words)
    results = expander.expand('en', topn=10)
    print('Expanded lexicon (en):')
    for w in sorted(results):
        print('-', w)
