import pgf

gr = pgf.readPGF("Parse.pgf")
print(gr.languages.keys())
eng = gr.languages["ParseEng"]

example = "the cat sat on the mat"

# parse into tree
i = eng.parse(example)
tree, expr = i.__next__()
print(eng.graphvizParseTree(expr))

print("Original tree:", expr)
print("Original sentence:", eng.linearize(expr))

# recursively find verb phrases
def find_tense(expr):
    tenses = ['ComplVPS2']
    exprs = []
    fun, args = expr.unpack()
    if fun in tenses:
        exprs.append(expr)
        print(expr)
    for arg in args:
        exprs.extend(find_tense(arg))
    return exprs

print(find_tense(expr))