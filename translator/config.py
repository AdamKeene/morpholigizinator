DB_PATH = "./gf_wordnet.db"
OUTPUT_DIR = "./resources/DomainLexicon"

GF_WORDNET_DIR = "/usr/share/gf-3.11/gf-wordnet"
GF_WORDNET_BUILD_GFO = "/usr/share/gf-3.11/gf-wordnet/build/gfo"

LANG_CONFIG = {
    "en": {
        "spacy_model": "en_core_web_sm",
        "fasttext_vec": "./resources/cc.en.300.vec",
        "gf_suffix": "Eng",
        "gf_cat_module": "CatEng",
        "gf_open": (
            "MorphoEng, ResEng, ParadigmsEng, IrregEng, ExtraEng, "
            "(G = GrammarEng), (C = ConstructX), Prelude"
        ),
        "gf_db_column": "eng_lin",
        "gf_zero_morph": False,
    },
    "es": {
        "spacy_model": "es_core_news_sm",
        "fasttext_vec": "./resources/cc.es.300.vec",
        "gf_suffix": "Spa",
        "gf_cat_module": "CatSpa",
        "gf_open": (
            "ConstructionSpa, GrammarSpa, ParadigmsSpa, ParamX, "
            "(S = StructuralSpa), (E = ExtendSpa), (L = LexiconSpa), "
            "(I = IrregSpa), (M = MorphoSpa), (R = ResSpa), Prelude"
        ),
        "gf_db_column": "spa_lin",
        "gf_zero_morph": False,
    },
    "de": {
        "spacy_model": "de_core_news_sm",
        "fasttext_vec": "./resources/cc.de.300.vec",
        "gf_suffix": "Ger",
        "gf_cat_module": "CatGer",
        "gf_open": (
            "Prelude, ParadigmsGer, GrammarGer, "
            "(M = MorphoGer), (S = StructuralGer), (ResGer = ResGer)"
        ),
        "gf_db_column": None,
        "gf_zero_morph": False,
    },
    "ja": {
        "spacy_model": "ja_core_news_sm",
        "fasttext_vec": "./resources/cc.ja.300.vec",
        "gf_suffix": "Jpn",
        "gf_cat_module": "CatZero",
        "gf_open": "ParadigmsZero",
        "gf_db_column": None,
        "gf_zero_morph": True,
    },
    # Add more languages here. For full RGL support set gf_cat_module = "Cat{Suffix}",
    # gf_zero_morph = False. For surface-form only set gf_cat_module = "CatZero",
    # gf_open = "ParadigmsZero", gf_zero_morph = True.
}

MARIAN_MODELS = {
    "en-es": "Helsinki-NLP/opus-mt-en-es",
    "es-en": "Helsinki-NLP/opus-mt-es-en",
    "de-es": "Helsinki-NLP/opus-mt-de-es",
    "es-de": "Helsinki-NLP/opus-mt-es-de",
    "en-de": "Helsinki-NLP/opus-mt-en-de",
    "de-en": "Helsinki-NLP/opus-mt-de-en",
    "en-ja": "Helsinki-NLP/opus-mt-en-ja",
    "ja-en": "Helsinki-NLP/opus-mt-ja-en",
}
M2M100_MODEL = "facebook/m2m100_418M"

SPACY_TO_GF = {
    "NOUN": "N",
    "PROPN": "PN",
    "VERB": "V2",
    "ADJ": "A",
    "ADV": "Adv",
}
DEFAULT_GF_CAT = "N"

# Default run parameters — override via build_grammar() kwargs or __main__
SOURCE_LANG = "ja"
TARGET_LANGS = ["en", "es", "de", "ja"]
SOURCE_TEXT_PATH = "./resources/sample_document_ja.txt"
MODULE_NAME = "DomainLexicon"
NUM_TOPICS = 5
WORDS_PER_TOPIC = 5
TOP_N_SIMILAR = 20
