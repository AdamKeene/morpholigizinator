# https://www.grammaticalframework.org/lib/doc/absfuns.html

import pgf
import re

grammar = pgf.readPGF("Parse.pgf")
lang = grammar.languages["ParseEng"]

def print_tree(node, indent=0):
    if isinstance(node, tuple):
        print('  ' * indent + str(node[0]))
        for child in node[1]:
            print_tree(child.unpack(), indent + 1)
    else:
        print('sack' + '  ' * indent + str(node))

def get_parse_tree(text):
    try:
        _, expr = next(lang.parse(text))
        tree = expr.unpack()
        print_tree(tree)
        return expr
    except Exception as e:
        print(f"Error: {e}")
        return None

tree_str = get_parse_tree("the cat sat on the mat and I ate my hat")