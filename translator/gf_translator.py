import itertools
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as _FuturesTimeout

import pgf
from sentence_transformers import SentenceTransformer
from sentence_transformers import util as st_util

from .config import LANG_CONFIG
from .nmt import translate_batch
from .pipeline import build_grammar

# Seconds to wait for a single GF parse before giving up.
# GF chart parsing on long/unusual input strings can take 30+ seconds;
# for lesson delivery this is unacceptable.  10s is generous for
# well-formed domain vocabulary strings.
_PARSE_TIMEOUT = 10.0

# Module-level executor so we don't pay thread-spawn cost per request.
_parse_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="gf_parse")

DOMAIN_PGF_PATH = "./resources/DomainLexicon/DomainTranslator.pgf"

# Cache loaded PGF grammars by path so repeated calls to translate() don't
# re-parse the binary on every invocation.
_domain_grammar_cache: dict = {}

# Reranking model — loaded once on first use, then kept in memory.
# paraphrase-multilingual-MiniLM-L12-v2:
#   ~400MB, 50+ languages, optimised for semantic similarity of short texts.
#   Multilingual support is important here because we're comparing source-language
#   phrases against NMT back-translations, which are also in the source language.
_RERANK_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
_rerank_model: SentenceTransformer | None = None


def _load_rerank_model() -> SentenceTransformer:
    global _rerank_model
    if _rerank_model is None:
        print(f"  Loading rerank model {_RERANK_MODEL_NAME} (downloading if not cached)...")
        _rerank_model = SentenceTransformer(_RERANK_MODEL_NAME)
        print("  Rerank model loaded.")
    return _rerank_model


class TranslationResult:
    """
    Returned by the translator callable from translate_document().
    Behaves as a plain string but also exposes .text and .method ("gf" or "nmt").
    """
    __slots__ = ("text", "method")

    def __init__(self, text: str, method: str):
        self.text = text
        self.method = method

    def __str__(self):
        return self.text

    def __repr__(self):
        return f"TranslationResult({self.text!r}, method={self.method!r})"


def _timed_parse(concrete, text: str, n: int = 20) -> list:
    """
    Parse text and return up to n (prob, expr) pairs, with a timeout.

    Runs the GF chart parser in a worker thread so that the calling thread
    (a web worker) is not blocked indefinitely by pathological inputs.

    Raises TimeoutError if the parse takes longer than _PARSE_TIMEOUT seconds.
    The background thread continues in daemon mode — it will not block server
    shutdown.
    """
    future = _parse_executor.submit(
        lambda: list(itertools.islice(concrete.parse(text), n))
    )
    try:
        return future.result(timeout=_PARSE_TIMEOUT)
    except _FuturesTimeout:
        raise TimeoutError(
            f"GF parse timed out after {_PARSE_TIMEOUT}s for: {text!r}"
        )


def _load_domain_grammar(pgf_path=DOMAIN_PGF_PATH):
    if pgf_path not in _domain_grammar_cache:
        try:
            _domain_grammar_cache[pgf_path] = pgf.readPGF(pgf_path)
        except Exception as e:
            raise RuntimeError(
                f"Could not load {pgf_path}. Run pipeline.build_grammar first.\n{e}"
            )
    return _domain_grammar_cache[pgf_path]


def _get_src_tgt(grammar, source_lang, target_lang):
    """Return (src_concrete, tgt_concrete) from a loaded grammar."""
    src_name = f"DomainTranslator{LANG_CONFIG[source_lang]['gf_suffix']}"
    tgt_name = f"DomainTranslator{LANG_CONFIG[target_lang]['gf_suffix']}"
    if src_name not in grammar.languages:
        raise ValueError(f"{src_name} not in grammar — recompile with '{source_lang}' in target_langs")
    if tgt_name not in grammar.languages:
        raise ValueError(f"{tgt_name} not in grammar — recompile with '{target_lang}' in target_langs")
    return grammar.languages[src_name], grammar.languages[tgt_name]


def translate(text, source_lang, target_lang, pgf_path=DOMAIN_PGF_PATH):
    """Parse text in source_lang and linearize in target_lang. Returns first parse."""
    grammar = _load_domain_grammar(pgf_path)
    src_lang, tgt_lang = _get_src_tgt(grammar, source_lang, target_lang)
    pairs = _timed_parse(src_lang, text, n=1)
    if not pairs:
        raise ValueError(f"No parse found for: {text!r}")
    _, expr = pairs[0]
    return tgt_lang.linearize(expr)


def translate_all(text, source_lang, target_lang, pgf_path=DOMAIN_PGF_PATH, n=5):
    """Return up to n alternative translations ranked by GF parse probability."""
    grammar = _load_domain_grammar(pgf_path)
    src_lang, tgt_lang = _get_src_tgt(grammar, source_lang, target_lang)
    pairs = _timed_parse(src_lang, text, n=n * 4)
    results = []
    for _, expr in pairs:
        lin = tgt_lang.linearize(expr)
        if '[' not in lin:  # skip incomplete linearizations (unresolved abstract names)
            results.append(lin)
        if len(results) >= n:
            break
    return results


def _semantic_scores(original: str, back_translations: list[str]) -> list[float]:
    """
    Score each back-translation against the original using multilingual
    semantic embeddings.

    All texts are encoded in a single batch — the original is the first
    element, back-translations follow. Cosine similarity is computed between
    the original embedding and each back-translation embedding.

    This handles cases that token overlap misses:
    - Morphological variants: "corre" vs "correr" score as similar
    - Synonyms: "trota" vs "corre" (both mean "runs") score higher than
      "lanza" (throws)
    - Word order variation in inflected languages

    Falls back to token overlap if the model fails to load or encode.
    """
    try:
        model = _load_rerank_model()
        all_texts = [original] + back_translations
        embeddings = model.encode(all_texts, convert_to_tensor=True)
        orig_emb = embeddings[0]
        bt_embs = embeddings[1:]
        similarities = st_util.cos_sim(orig_emb, bt_embs)[0]
        return similarities.tolist()
    except Exception:
        # Degrade gracefully to token overlap if anything goes wrong
        orig_tokens = set(original.lower().split())
        scores = []
        for bt in back_translations:
            bt_tokens = set(bt.lower().split())
            scores.append(len(orig_tokens & bt_tokens) / max(len(orig_tokens), 1))
        return scores


def translate_reranked(text, source_lang, target_lang, pgf_path=DOMAIN_PGF_PATH, n=5):
    """
    Get up to n GF parses, rerank by round-trip semantic fidelity, return best.

    GF grammars can produce multiple valid parses for the same input string
    (structural ambiguity). The highest-probability GF parse is not always the
    most natural translation. This function:
      1. Back-translates every candidate from target → source via NMT
      2. Encodes the original and all back-translations with a multilingual
         sentence embedding model
      3. Returns the candidate whose back-translation is most semantically
         similar to the original phrase

    Falls back to the top GF parse if back-translation or scoring fails.
    """
    candidates = translate_all(text, source_lang, target_lang, pgf_path, n)
    if not candidates:
        raise ValueError(f"No parse found for: {text!r}")
    if len(candidates) == 1:
        return candidates[0]
    try:
        t = time.perf_counter()
        back_translations = translate_batch(candidates, target_lang, source_lang)
        nmt_time = time.perf_counter() - t

        t = time.perf_counter()
        scores = _semantic_scores(text, back_translations)
        score_time = time.perf_counter() - t

        print(f"  [rerank] {len(candidates)} candidates: NMT {nmt_time:.2f}s, scoring {score_time:.3f}s")
        return candidates[scores.index(max(scores))]
    except Exception:
        return candidates[0]


def _apply_surface_map(text, token_map):
    """
    Replace untranslated source-language tokens in NMT output using the
    domain surface map.

    When NMT is used as a fallback, known domain words (from Wiktionary entries
    and build_generated_entries) may not be translated correctly by the NMT model.
    This substitutes them word-by-word, preserving any surrounding punctuation.

    token_map : {source_surface_lower: target_surface}
    """
    if not token_map:
        return text
    words = text.split()
    result = []
    for word in words:
        stripped = word.lower().strip(".,!?;:'\"")
        if stripped in token_map:
            # Count leading and trailing punctuation characters so we can
            # reattach them to the replacement word.
            n_prefix = len(word) - len(word.lstrip(".,!?;:'\""))
            prefix = word[:n_prefix]
            suffix = word[len(word.rstrip(".,!?;:'\"")):]
            result.append(prefix + token_map[stripped] + suffix)
        else:
            result.append(word)
    return " ".join(result)


def translate_document(doc, source_lang, target_lang, verbose=False):
    """
    Build a domain grammar from doc, then return a translator callable.

    Pipeline summary:
      1. build_grammar() runs the full extraction → lookup → GF compile chain.
      2. The returned callable tries GF first (precise, grammar-based).
      3. On GF failure (phrase not in grammar), falls back to NMT with
         _apply_surface_map to fix known domain words the NMT model may miss.

    Usage:
        translator = translate_document("path/to/doc.srt", "es", "en")
        result = translator("el pingüino corre")
        print(result, result.method)  # "the penguin runs" gf
    """
    pgf_path, surface_map = build_grammar(doc, source_lang, [source_lang, target_lang])
    token_map = surface_map.get(target_lang, {})
    # Evict any stale cached grammar so the freshly compiled .pgf is loaded
    _domain_grammar_cache.pop(pgf_path, None)

    def translator(phrase):
        try:
            text = translate_reranked(phrase, source_lang, target_lang, pgf_path)
            return TranslationResult(text, "gf")
        except (ValueError, StopIteration, pgf.ParseError, TimeoutError):
            if verbose:
                print(f"  GF miss — falling back to NMT for: {phrase!r}")
            text = translate_batch([phrase], source_lang, target_lang)[0]
            text = _apply_surface_map(text, token_map)
            return TranslationResult(text, "nmt")

    return translator
