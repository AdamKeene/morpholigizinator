# Compatibility shim — code has moved to the translator/ package.
from translator import translate_document, translate, translate_all, translate_reranked, TranslationResult
from translator.gf_translator import (
    get_tree_expr, get_tree, get_expr,
    substitute_one, substitute_all, cartesian_substitution, separate_clause,
    _apply_surface_map,
)
