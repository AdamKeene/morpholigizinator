import pgf
from chart import cats
from itertools import product

langs = {
    "es": "ParseSpa",
    "en": "ParseEng",
}

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