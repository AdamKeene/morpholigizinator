OUTPUT_DIR = "./resources/DomainLexicon"

# ---------------------------------------------------------------------------
# Language configuration
# ---------------------------------------------------------------------------
# Each entry controls how the pipeline handles a language:
#   spacy_model    : spaCy model for tokenisation/POS tagging (must be installed)
#   fasttext_vec   : path to a fastText .vec file for semantic expansion
#   gf_suffix      : GF language suffix (e.g. "Spa" → ParseSpa, CatSpa)
#   gf_cat_module  : RGL category module opened in concrete files.
#                    Full-morphology languages use "Cat{Suffix}" (Eng, Spa, Ger).
#                    Zero-morphology languages (Jpn) use "CatZero" — the RGL
#                    CatZero module accepts any surface string without inflection.
#   gf_open        : comma-separated RGL modules to open in concrete lin sections
#   gf_zero_morph  : True → _make_lin_expr uses the simpler mkN/mkV/... form
#                    that works without paradigm tables (required for CatZero).
# ---------------------------------------------------------------------------
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
        "gf_zero_morph": False,
        "gf_verb_suffixes": None,       # no restriction on English infinitive form
        # --- Runtime behaviour flags ---
        # slow_source_parse  : GF parse() is fast; use it for source analysis
        # word_boundary_search: use \b in source-sentence keyword search
        # spacy_sym_filter   : do NOT filter SYM POS tokens (not needed for English)
        # source_pattern_method: use GF parse() to extract GrammarPatterns
        # compound_splitting : no productive compounding in English
        # apertium_to_en     : no bridge needed — English IS the bridge language
        "slow_source_parse":     False,
        "word_boundary_search":  True,
        "spacy_sym_filter":      False,
        "source_pattern_method": "gf",
        "compound_splitting":    False,
        "apertium_to_en":        False,
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
        "gf_zero_morph": False,
        "gf_verb_suffixes": ("ar", "ir", "er"),   # ParadigmsSpa.mkV constraint
        # --- Runtime behaviour flags ---
        "slow_source_parse":     False,
        "word_boundary_search":  True,
        "spacy_sym_filter":      False,
        "source_pattern_method": "gf",
        "compound_splitting":    False,
        "apertium_to_en":        True,
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
        "gf_zero_morph": False,
        "gf_verb_suffixes": ("en", "eln", "ern"),  # ParadigmsGer.mkV constraint
        # --- Runtime behaviour flags ---
        # slow_source_parse: GF parse() is ~15 s/sentence for German (compound
        #   splitting rules in the RGL).  Use spaCy dep-parse instead.
        # compound_splitting: German forms compounds productively; many domain
        #   nouns (Elektroauto, Ladekabel) are compounds whose head is in WordNet.
        "slow_source_parse":     True,
        "word_boundary_search":  True,
        "spacy_sym_filter":      False,
        "source_pattern_method": "spacy_dep",
        "compound_splitting":    True,
        "apertium_to_en":        True,
    },
    "ja": {
        "spacy_model": "ja_core_news_sm",
        "fasttext_vec": "./resources/cc.ja.300.vec",
        "gf_suffix": "Jpn",
        # CatJpn (not CatZero) must be used so that DomainLexiconJpn is
        # compatible with ParseJpn when combined in DomainTranslatorJpn.
        # CatZero and CatJpn define the same abstract categories with different
        # record structures — mixing them causes "cannot unify" at link time.
        "gf_cat_module": "CatJpn",
        "gf_open": "ParadigmsJpn, (S = StructuralJpn), Prelude",
        "gf_zero_morph": True,   # simple mkN/mkV calls work with ParadigmsJpn
        "gf_verb_suffixes": None,  # Japanese verbs have no fixed infinitive ending
        # --- Runtime behaviour flags ---
        # slow_source_parse: GF ParseJpn parse() is unreliable for source text.
        # word_boundary_search: Japanese has no word boundaries; use substring match.
        # spacy_sym_filter: spaCy's Japanese model tags script/punctuation as SYM;
        #   filtering prevents junk tokens reaching the LDA topic model.
        # source_pattern_method: spaCy + GiNZA (SudachiPy) dep-parse. Detects tense,
        #   polarity, ている progressive, を object particle, and question form.
        #   Person is not extracted (Japanese lacks grammatical person marking).
        # apertium_to_en: Apertium ja-en support exists but is limited.
        "slow_source_parse":     True,
        "word_boundary_search":  False,
        "spacy_sym_filter":      True,
        "source_pattern_method": "spacy_dep",
        "compound_splitting":    False,
        "apertium_to_en":        True,
    },
    # ---------------------------------------------------------------------------
    # Template for adding a new language:
    #
    # "xx": {
    #     "spacy_model":           "xx_core_news_sm",      # spaCy model name
    #     "fasttext_vec":          "./resources/cc.xx.300.vec",
    #     "gf_suffix":             "Xxx",                  # GF concrete suffix
    #     "gf_cat_module":         "CatXxx",               # or "CatZero"
    #     "gf_open":               "ParadigmsXxx, Prelude",
    #     "gf_zero_morph":         False,                  # True for no-morphology langs
    #     "gf_verb_suffixes":      None,                   # or tuple of valid infinitive endings
    #     "slow_source_parse":     False,   # True if GF parse() > ~2 s/sentence
    #     "word_boundary_search":  True,    # False for script languages (Japanese, Chinese…)
    #     "spacy_sym_filter":      False,   # True if spaCy SYM tokens are junk for this lang
    #     "source_pattern_method": "gf",   # "gf" | "spacy_dep" | "none"
    #     "compound_splitting":    False,   # True for productively compounding languages
    #     "apertium_to_en":        True,    # False only for English (the bridge language)
    # },
    # ---------------------------------------------------------------------------
}

# ---------------------------------------------------------------------------
# NMT model registry
# ---------------------------------------------------------------------------
# Helsinki-NLP Marian models are preferred for supported pairs — fast,
# small, and accurate for common European languages.
# For pairs without a direct Marian model, M2M-100 (multilingual) is used
# as a fallback. M2M-100 is significantly larger and slower.
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

# ---------------------------------------------------------------------------
# spaCy POS → GF category mapping
# ---------------------------------------------------------------------------
# GF categories: N (noun), PN (proper noun), V2 (transitive verb),
# V (intransitive verb), A (adjective), Adv (adverb).
# Verbs default to V2 since most content verbs in natural text take objects.
SPACY_TO_GF = {
    "NOUN": "N",
    "PROPN": "PN",
    "VERB": "V2",
    "ADJ": "A",
    "ADV": "Adv",
}
DEFAULT_GF_CAT = "N"

# ---------------------------------------------------------------------------
# Default run parameters — CLI / pipeline.py __main__ only
#
# The web layer does NOT use these.  build_grammar() and build_lesson() are
# called with the specific (source_lang, target_lang) pair for the requesting
# user — never all languages at once.  Compiling all concretes is wasteful
# and makes the GF compile significantly slower.
# ---------------------------------------------------------------------------
SOURCE_LANG = "ja"
TARGET_LANGS = ["en", "es", "de", "ja"]
SOURCE_TEXT_PATH = "./resources/sample_document_ja.txt"
MODULE_NAME = "DomainLexicon"
NUM_TOPICS = 5
WORDS_PER_TOPIC = 5
TOP_N_SIMILAR = 20
