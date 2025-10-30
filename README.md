# Morpholigizinator

An in-progress sentence morphology toolkit using Grammatical Framework. Hybrid translation coming soon.

## Usage: 

### Substitution:

Substitution functions take an input of one or more lists of gf symbols and replaces items from the list with the other list items, allowing for changing tenses, word forms, and more. General use input lists will be available soon.

These substitutions can be done for just one symbol, separately for each matching symbol, or for all possible combinations of symbols

Keep in mind substitution functions return a GF abstract syntax tree and not the output phrases themselves. To get those, iterate through the tree.

Use substitute_one to replace one symbol

```python
cats = ["TPres", "TPast", "TFut", "TPastSimple"]
expr = "the cat sat on the mat"
new_trees = substitute_one(expr, cats)
for tree in new_trees:
    print(lang.linearize(tree))

# the cat sits on the mat
# the cat sat on the mat
# the cat will sit on the mat
```

Use substitute_all to replace all symbols

```python
for tree in substitute_all(expr, cats):
    print(lang.linearize(tree))

# the cat sat on the mat
# the cats sat on the mats
```

Use cartesian_substitution to generate all possible replacement combinations

```python
example_categories = [
    ["TPres", "TPast", "TFut", 'TPastSimple'],
    ["NumSg", "NumPl"],
    ["DefArt", "IndefArt"]
]

all_trees = cartesian_substitution(expr, example_categories)
for t in all_trees:
    print(lang.linearize(t))

# the cat sits on the mat
# the cat sits on the mats
# the cat sits on a mat
# the cat sits on mats
# the cat sat on the mat
# the cat sat on the mats
#...64 results
```

### Clause Extraction:

Use separate_clause to extract clauses from larger bodies of text. This extracts text according to grammar rules, not context relevant n-grams or text samples.

This function uses the grammar_categories db which contains category names flagged as clauses, custom identifiers can be passed through the cats flag

```python
example_text = "The cat sat on the mat and ate my hat, he sat on the mat and ate my hat."
clauses = separate_clause(example_expr)
for clause in clauses:
    print(lang.linearize(clause))
# the cat sat on the mat and ate my hat, he sat on the mat and ate my hat
# the cat sat on the mat and ate my hat, he sat on the mat and ate my hat
# the cat sat on the mat and ate my hat, he sat on the mat
# the cat sat on the mat and ate my hat
# he sat on the mat
# he sat on the mat
# ate my hat
```