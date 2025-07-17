import pgf
from chart import cats
from itertools import product

grammar = pgf.readPGF("EnEsParse.pgf")
lang = grammar.languages["ParseSpa"]

example = "El gato se sentó en la alfombra"
i = lang.parse(example)
tree, expr = i.__next__()

example_categories = [
    ["TPres", "TPast", "TFut", 'TPastSimple'],
    ["NumSg", "NumPl"],
    ["DefArt", "IndefArt"]
]

def get_category(fun, cats):
    for cat in cats:
        if fun in cat:
            return cat
    return None

# only substitutes first valid item
def substitute_one(expr, cats):
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

new_trees = substitute_one(expr, example_categories[0])
for tree in new_trees:
    print("first", lang.linearize(tree))

# complete all valid substitutions for the whole text
def substitute_all(expr, category):
    def replace(expr, target_fun):
        fun, args = expr.unpack()
        if fun in category:
            fun = target_fun
        new_args = [replace(arg, target_fun) for arg in args]
        return pgf.Expr(fun, new_args)
    return [replace(expr, alt) for alt in category]

# generate all possible combinations
def cartesian_substitution(expr, cats):
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

# substitution examples
# all_trees = cartesian_substitution(expr, example_categories)
# for t in all_trees:
#     print("cart", lang.linearize(t))

# for tree in substitute_all(expr, example_categories[0]):
#     print("all", lang.linearize(tree))

def separate_clause(expr, cats=cats):
    fun, args = expr.unpack()
    results = []
    if fun in cats['all_clauses']:
        print('cl:', fun)
        results.append(expr)
    for arg in args:
        results.extend(separate_clause(arg))
    return results

    # #example separation
    # example = "the cat sat on the mat and ate my hat, you sat on the mat and ate a hat"
    # i = lang.parse(example)
    # tree, expr = i.__next__()
    # clause_trees = separate_clause(expr)
    # for clause in clause_trees:
    #     print("cl", lang.linearize(clause))
