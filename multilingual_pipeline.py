# Compatibility shim — code has moved to the translator/ package.
from translator.pipeline import build_grammar
from translator.wordnet import (
    build_wordnet_index, wordnet_lookup, fill_missing_lins, build_generated_entries,
)
from translator.keywords import extract_keywords
from translator.expansion import semantic_expansion
from translator.nmt import translate_batch
from translator.gf_writer import generate_gf_files, generate_translator_files, compile_grammar
from translator.config import (
    LANG_CONFIG, MARIAN_MODELS, M2M100_MODEL, SPACY_TO_GF, DEFAULT_GF_CAT,
    DB_PATH, OUTPUT_DIR, GF_WORDNET_DIR, SOURCE_LANG, TARGET_LANGS,
    SOURCE_TEXT_PATH, MODULE_NAME, NUM_TOPICS, WORDS_PER_TOPIC, TOP_N_SIMILAR,
)
