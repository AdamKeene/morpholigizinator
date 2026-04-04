# Compatibility shim — code has moved to the translator/ package.
from translator import translate_document, translate, translate_all, translate_reranked, TranslationResult
from translator.gf_translator import _apply_surface_map
