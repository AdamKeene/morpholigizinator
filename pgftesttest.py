import pgf
import re

grammar = pgf.readPGF("Parse.pgf")
lang = grammar.languages["ParseEng"]

categories = [
    ["TPres", "TPast", "TFut"],
    ["NumSg", "NumPl"],
    ["DefArt", "IndefArt"]
]

def process_tree(node, count=0):
    results = []
    if isinstance(node, tuple):
        for cat in categories:
            if node[0] in categories:
                for alt in cat:
                    if alt != node[0]:
                        results.extend(process_tree(alt, count + 1))

        for child in node[1]:
            results.extend(process_tree(child.unpack(), count + 1))
    else:
        print('sack' + '  ' * count + str(node))

def get_parse_tree(text):
    try:
        _, expr = next(lang.parse(text))
        tree = expr.unpack()
        process_tree(tree)
        return expr
    except Exception as e:
        print(f"Error: {e}")
        return None

tree_str = get_parse_tree("the cat sits on the mat")