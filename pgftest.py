import pgf

grammar = pgf.readPGF("Parse.pgf")
lang = grammar.languages["ParseEng"]

example = "the cat sat on the mat"
i = lang.parse(example)
tree, expr = i.__next__()
print(lang.graphvizParseTree(expr))

categories = [
    ["TPres", "TPast", "TFut", 'TPastSimple'],
    ["NumSg", "NumPl"],
    ["DefArt", "IndefArt"]
]

def substitute_once(expr, rules):
    fun, args = expr.unpack()
    results = []

    # If this node matches the target, generate a new tree for each replacement
    if fun in rules:
        for alt in rules:
            if alt != fun:
                results.append(pgf.Expr(alt, args))
        return results

    # Otherwise, recurse into children
    for idx, arg in enumerate(args):
        for new_arg in substitute_once(arg, rules):
            new_args = list(args)
            new_args[idx] = new_arg
            results.append(pgf.Expr(fun, new_args))
    return results

new_trees = substitute_once(expr, categories[0])
for tree in new_trees:
    print(lang.linearize(tree))