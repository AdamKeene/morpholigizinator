import pgf
from itertools import product

from chart import cats

from .config import LANG_CONFIG
from .nmt import translate_batch
from .pipeline import build_grammar

DOMAIN_PGF_PATH = "./resources/DomainLexicon/DomainTranslator.pgf"

_domain_grammar_cache: dict = {}


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
    try:
        _, expr = next(src_lang.parse(text))
    except StopIteration:
        raise ValueError(f"No parse found for: {text!r}")
    return tgt_lang.linearize(expr)


def translate_all(text, source_lang, target_lang, pgf_path=DOMAIN_PGF_PATH, n=5):
    """Return up to n alternative translations ranked by GF parse probability."""
    grammar = _load_domain_grammar(pgf_path)
    src_lang, tgt_lang = _get_src_tgt(grammar, source_lang, target_lang)
    results = []
    for i, (_, expr) in enumerate(src_lang.parse(text)):
        if i >= n:
            break
        results.append(tgt_lang.linearize(expr))
    return results


def _roundtrip_score(original, back_translation):
    """Token overlap between original and back-translated text (0–1)."""
    orig = set(original.lower().split())
    back = set(back_translation.lower().split())
    if not orig:
        return 0.0
    return len(orig & back) / len(orig)


def translate_reranked(text, source_lang, target_lang, pgf_path=DOMAIN_PGF_PATH, n=5):
    """
    Get up to n GF parses, rerank by round-trip NMT fidelity, return best.
    Falls back to the top GF parse if back-translation fails.
    """
    import time
    candidates = translate_all(text, source_lang, target_lang, pgf_path, n)
    if not candidates:
        raise ValueError(f"No parse found for: {text!r}")
    if len(candidates) == 1:
        return candidates[0]
    try:
        t = time.perf_counter()
        back_translations = translate_batch(candidates, target_lang, source_lang)
        print(f"  [rerank] NMT back-translation of {len(candidates)} candidates: {time.perf_counter()-t:.2f}s")
        scores = [_roundtrip_score(text, bt) for bt in back_translations]
        return candidates[scores.index(max(scores))]
    except Exception:
        return candidates[0]


def _apply_surface_map(text, token_map):
    """Replace untranslated source-language tokens using the domain surface map."""
    if not token_map:
        return text
    words = text.split()
    result = []
    for word in words:
        stripped = word.lower().strip(".,!?;:'\"")
        if stripped in token_map:
            prefix = word[: len(word) - len(word.lstrip(".,!?;:'\""))]
            suffix = word[len(word.rstrip(".,!?;:'\"")):]
            result.append(prefix + token_map[stripped] + suffix)
        else:
            result.append(word)
    return " ".join(result)


def translate_document(doc, source_lang, target_lang, verbose=False):
    """
    Build a domain grammar from doc, then return a translator callable.

    The returned callable tries GF first (precise, grammar-based) and falls
    back to NMT for phrases GF cannot parse.

    Usage:
        translator = translate_document("path/to/doc.srt", "es", "en")
        result = translator("el pingüino corre")
        print(result, result.method)
    """
    pgf_path, surface_map = build_grammar(doc, source_lang, [source_lang, target_lang])
    token_map = surface_map.get(target_lang, {})
    _domain_grammar_cache.pop(pgf_path, None)

    def translator(phrase):
        try:
            text = translate_reranked(phrase, source_lang, target_lang, pgf_path)
            return TranslationResult(text, "gf")
        except (ValueError, StopIteration, pgf.ParseError):
            if verbose:
                print(f"  GF miss — falling back to NMT for: {phrase!r}")
            text = translate_batch([phrase], source_lang, target_lang)[0]
            text = _apply_surface_map(text, token_map)
            return TranslationResult(text, "nmt")

    return translator


# ---------------------------------------------------------------------------
# GF tree utilities — grammar-level manipulation and analysis
# ---------------------------------------------------------------------------

def get_tree_expr(text, lang):
    tree, expr = next(lang.parse(text))
    return tree, expr


def get_tree(text, lang):
    tree, _ = get_tree_expr(text, lang)
    return tree


def get_expr(text, lang):
    _, expr = get_tree_expr(text, lang)
    return expr


def _get_category(fun, cats):
    for cat in cats:
        if fun in cat:
            return cat
    return None


def substitute_one(expr, cats=cats):
    """Substitute the first matching node in expr with all alternatives."""
    fun, args = expr.unpack()
    results = []
    if fun in cats:
        return [pgf.Expr(alt, args) for alt in cats if alt != fun]
    for i, arg in enumerate(args):
        for new_arg in substitute_one(arg, cats):
            new_args = list(args)
            new_args[i] = new_arg
            results.append(pgf.Expr(fun, new_args))
    return results


def substitute_all(expr, cats=cats):
    """Replace every matching node in expr with each alternative."""
    def replace(expr, target_fun):
        fun, args = expr.unpack()
        if fun in cats:
            fun = target_fun
        return pgf.Expr(fun, [replace(arg, target_fun) for arg in args])

    if cats and isinstance(cats[0], list):
        results = []
        for cat in cats:
            fun, _ = expr.unpack()
            results.extend([replace(expr, alt) for alt in cat if alt != fun])
        return results
    else:
        fun, _ = expr.unpack()
        return [replace(expr, alt) for alt in cats if alt != fun]


def cartesian_substitution(expr, cats=cats):
    """Generate all possible substitution combinations across the whole tree."""
    fun, args = expr.unpack()
    cat = _get_category(fun, cats)
    children_options = [cartesian_substitution(arg, cats) for arg in args]
    children_combinations = list(product(*children_options)) if children_options else [()]
    results = []
    if cat:
        for alt in cat:
            for combo in children_combinations:
                results.append(pgf.Expr(alt, list(combo)))
    else:
        for combo in children_combinations:
            results.append(pgf.Expr(fun, list(combo)))
    return results


def separate_clause(expr, cats=cats):
    """Recursively extract all clause-level sub-expressions from a parse tree."""
    fun, args = expr.unpack()
    results = []
    if fun in cats['all_clauses']:
        results.append(expr)
    for arg in args:
        results.extend(separate_clause(arg, cats))  # cats passed through explicitly
    return results
