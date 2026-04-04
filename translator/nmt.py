from transformers import (
    AutoTokenizer,
    AutoModelForSeq2SeqLM,
    MarianTokenizer,
    MarianMTModel,
    logging as hf_logging,
)

from .config import MARIAN_MODELS, M2M100_MODEL

# Suppress the "weights tied" warning that Marian models emit on every load.
# It is informational (not an error) and not actionable.
hf_logging.set_verbosity_error()

# Cache loaded models by "source-target" key so each pair is only downloaded
# and initialised once per process.
_nmt_model_cache: dict = {}


def _load_nmt_model(source_lang, target_lang):
    """
    Load the appropriate NMT model for a language pair.

    Preference order:
    1. Helsinki-NLP Marian model (fast, ~300MB, purpose-built for the pair)
    2. Facebook M2M-100 418M (multilingual fallback, larger, slower)

    Models are downloaded from Hugging Face Hub on first use and cached to
    ~/.cache/huggingface/hub by the transformers library.
    """
    key = f"{source_lang}-{target_lang}"
    if key not in _nmt_model_cache:
        model_name = MARIAN_MODELS.get(key)
        if model_name:
            print(f"  Loading NMT model {model_name} (downloading if not cached)...")
            tokenizer = MarianTokenizer.from_pretrained(model_name)
            model = MarianMTModel.from_pretrained(model_name)
        else:
            print(f"  No direct model for {key}, using M2M-100")
            model_name = M2M100_MODEL
            print(f"  Loading NMT model {model_name} (downloading if not cached)...")
            tokenizer = AutoTokenizer.from_pretrained(model_name)
            model = AutoModelForSeq2SeqLM.from_pretrained(model_name)
            tokenizer.src_lang = source_lang
        print("  Model loaded.")
        _nmt_model_cache[key] = (tokenizer, model, model_name)
    return _nmt_model_cache[key]


def translate_batch(words, source_lang, target_lang):
    """
    Translate a list of words/phrases from source_lang to target_lang.
    Returns a list of translated strings in the same order as input.

    Processing is done in batches of 64 to keep GPU/CPU memory bounded.
    M2M-100 requires a forced BOS token set to the target language ID;
    Marian models handle this internally via their tokeniser configuration.
    """
    if source_lang == target_lang:
        return list(words)

    tokenizer, model, model_name = _load_nmt_model(source_lang, target_lang)

    translated = []
    batch_size = 64
    for i in range(0, len(words), batch_size):
        batch = list(words[i : i + batch_size])
        inputs = tokenizer(batch, return_tensors="pt", padding=True, truncation=True)
        # max_new_tokens bounds CPU time and prevents repetition loops that
        # NMT models produce for short/garbage inputs (e.g. "ng ng ng ...").
        # 64 tokens is far more than needed for any single word or short phrase.
        if model_name == M2M100_MODEL:
            out = model.generate(**inputs, forced_bos_token_id=tokenizer.get_lang_id(target_lang), max_new_tokens=64)
        else:
            out = model.generate(**inputs, max_new_tokens=64)
        translated.extend(tokenizer.decode(t, skip_special_tokens=True) for t in out)

    return translated
