import pgf
import spacy
from chart import cats
from itertools import product
from multilingual_pipeline import translate_batch, build_grammar, LANG_CONFIG


class TranslationResult:
    """
    Returned by the translator callable from translate_document().

    Behaves as a plain string in print() / str() contexts, but also exposes:
        .text    — the translated string
        .method  — "gf" or "nmt"

    Example:
        result = translator("Quiero ver ese arbol")
        print(result)           # prints the translation
        print(result.method)    # prints "gf" or "nmt"
    """
    __slots__ = ("text", "method")

    def __init__(self, text: str, method: str):
        self.text = text
        self.method = method

    def __str__(self):
        return self.text

    def __repr__(self):
        return f"TranslationResult({self.text!r}, method={self.method!r})"

langs = {
    "es": "ParseSpa",
    "en": "ParseEng",
}

# Mapping from language code to DomainTranslator concrete suffix
DOMAIN_SUFFIXES = {
    "en": "Eng",
    "es": "Spa",
    "de": "Ger",
    "ja": "Jpn",
}

DOMAIN_PGF_PATH = "./resources/DomainLexicon/DomainTranslator.pgf"

# Cache the loaded grammar so repeated calls don't reload from disk
_domain_grammar_cache = {}


def _load_domain_grammar(pgf_path=DOMAIN_PGF_PATH):
    if pgf_path not in _domain_grammar_cache:
        try:
            _domain_grammar_cache[pgf_path] = pgf.readPGF(pgf_path)
        except Exception as e:
            raise RuntimeError(
                f"Could not load {pgf_path}. Run multilingual_pipeline.py first.\n{e}"
            )
    return _domain_grammar_cache[pgf_path]


def translate(text, source_lang, target_lang, pgf_path=DOMAIN_PGF_PATH):
    """
    Parse `text` in `source_lang` and linearize in `target_lang` using the
    compiled DomainTranslator grammar.

    Returns the best translation string, or raises if no parse is found.
    """
    grammar = _load_domain_grammar(pgf_path)

    src_suffix = DOMAIN_SUFFIXES.get(source_lang)
    tgt_suffix = DOMAIN_SUFFIXES.get(target_lang)
    if not src_suffix:
        raise ValueError(f"Unknown source language: {source_lang!r}")
    if not tgt_suffix:
        raise ValueError(f"Unknown target language: {target_lang!r}")

    src_name = f"DomainTranslator{src_suffix}"
    tgt_name = f"DomainTranslator{tgt_suffix}"

    if src_name not in grammar.languages:
        raise ValueError(f"{src_name} not in grammar — recompile with '{source_lang}' in TARGET_LANGS")
    if tgt_name not in grammar.languages:
        raise ValueError(f"{tgt_name} not in grammar — recompile with '{target_lang}' in TARGET_LANGS")

    src_lang = grammar.languages[src_name]
    tgt_lang = grammar.languages[tgt_name]

    parses = src_lang.parse(text)
    try:
        _, expr = next(parses)
    except StopIteration:
        raise ValueError(f"No parse found for: {text!r}")

    return tgt_lang.linearize(expr)


def translate_all(text, source_lang, target_lang, pgf_path=DOMAIN_PGF_PATH, n=5):
    """
    Like translate(), but returns up to `n` alternative translations ranked by
    parse probability.
    """
    grammar = _load_domain_grammar(pgf_path)

    src_suffix = DOMAIN_SUFFIXES.get(source_lang)
    tgt_suffix = DOMAIN_SUFFIXES.get(target_lang)
    src_lang = grammar.languages[f"DomainTranslator{src_suffix}"]
    tgt_lang = grammar.languages[f"DomainTranslator{tgt_suffix}"]

    results = []
    for i, (_, expr) in enumerate(src_lang.parse(text)):
        if i >= n:
            break
        results.append(tgt_lang.linearize(expr))
    return results


# spaCy model cache
_nlp_cache = {}

def _get_nlp(lang_code):
    if lang_code not in _nlp_cache:
        model = LANG_CONFIG[lang_code]["spacy_model"]
        _nlp_cache[lang_code] = spacy.load(model)
    return _nlp_cache[lang_code]


def translate_document(doc, source_lang, target_lang, verbose=False):
    """
    Build a domain grammar from `doc`, then return a translator callable.

    Usage:
        translator = translate_document(doc, "en", "es")
        print(translator("the big battery"))

    The returned callable tries GF first (precise, grammar-based) and falls
    back to NMT for phrases GF cannot parse.

    doc         : raw text of the domain document used to build the lexicon
    source_lang : language code of the document and input phrases (e.g. "en")
    target_lang : language code to translate into (e.g. "es")
    """
    pgf_path = build_grammar(doc, source_lang, [source_lang, target_lang])

    # Invalidate the grammar cache so the newly compiled pgf is loaded fresh
    _domain_grammar_cache.pop(pgf_path, None)

    def translator(phrase):
        try:
            text = translate(phrase, source_lang, target_lang, pgf_path)
            return TranslationResult(text, "gf")
        except (ValueError, StopIteration, pgf.ParseError):
            if verbose:
                print(f"  GF miss — falling back to NMT for: {phrase!r}")
            text = translate_batch([phrase], source_lang, target_lang)[0]
            return TranslationResult(text, "nmt")

    return translator


def _get_lang(pgf_file, lang_name):
    grammar = pgf.readPGF(pgf_file)
    return grammar.languages[lang_name]

def _parse_text(text, lang=None, pgf_file=None, lang_name=None):
    if lang is None:
        lang = _get_lang(pgf_file, lang_name)
    return get_tree_expr(text, lang)

def get_tree_expr(text, lang=None, pgf_file=None, lang_name=None):
    if lang is None:
        lang = _get_lang(pgf_file, lang_name)
    i = lang.parse(text)
    tree, expr = i.__next__()
    return tree, expr

def get_tree(text, lang=None, pgf_file=None, lang_name=None):
    tree, _ = _parse_text(text, lang, pgf_file, lang_name)
    return tree

def get_expr(text, lang=None, pgf_file=None, lang_name=None):
    _, expr = _parse_text(text, lang, pgf_file, lang_name)
    return expr

#retrieve word categories from chart.py
def get_category(fun, cats):
    for cat in cats:
        if fun in cat:
            return cat
    return None

# only substitutes first valid item
def substitute_one(expr, cats=cats):
    fun, args = expr.unpack()
    results = []

    # make new tree
    if fun in cats:
        for alt in cats:
            if alt != fun:
                results.append(pgf.Expr(alt, args))
        return results

    # else recurse into children
    for i, arg in enumerate(args):
        for new_arg in substitute_one(arg, cats):
            new_args = list(args)
            new_args[i] = new_arg
            results.append(pgf.Expr(fun, new_args))
    return results

# complete all valid substitutions for the whole text
def substitute_all(expr, cats=cats):
    def replace(expr, target_fun):
        fun, args = expr.unpack()
        if fun in cats:
            fun = target_fun
        new_args = [replace(arg, target_fun) for arg in args]
        return pgf.Expr(fun, new_args)
    if type(cats[0]) == list:
        all_results = []
        for cat in cats:
            fun, _ = expr.unpack()
            all_results.extend([replace(expr, alt) for alt in cat if alt != fun])
        return all_results
    else:
        fun, _ = expr.unpack()
        return [replace(expr, alt) for alt in cats if alt != fun]

# generate all possible combinations
def cartesian_substitution(expr, cats=cats):
    fun, args = expr.unpack()
    cat = get_category(fun, cats)
    # Recursively get all combinations for children, get cartesian product of children
    children_options = [cartesian_substitution(arg, cats) for arg in args]
    children_combinations = list(product(*children_options)) if children_options else [()]
    results = []
    # make substitutions
    if cat:
        for alt in cat:
            for combo in children_combinations:
                results.append(pgf.Expr(alt, list(combo)))
    else:
        for combo in children_combinations:
            results.append(pgf.Expr(fun, list(combo)))
    return results

def separate_clause(expr, cats=cats):
    fun, args = expr.unpack()
    results = []
    if fun in cats['all_clauses']:
        results.append(expr)
    for arg in args:
        results.extend(separate_clause(arg))
    return results