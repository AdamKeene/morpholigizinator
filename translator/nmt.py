from transformers import (
    AutoTokenizer,
    AutoModelForSeq2SeqLM,
    MarianTokenizer,
    MarianMTModel,
    logging as hf_logging,
)

from .config import MARIAN_MODELS, M2M100_MODEL

hf_logging.set_verbosity_error()

_nmt_model_cache: dict = {}


def _load_nmt_model(source_lang, target_lang):
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
    Returns list of translated strings in the same order.
    """
    if source_lang == target_lang:
        return list(words)

    tokenizer, model, model_name = _load_nmt_model(source_lang, target_lang)

    translated = []
    batch_size = 64
    for i in range(0, len(words), batch_size):
        batch = list(words[i : i + batch_size])
        inputs = tokenizer(batch, return_tensors="pt", padding=True, truncation=True)
        if model_name == M2M100_MODEL:
            out = model.generate(**inputs, forced_bos_token_id=tokenizer.get_lang_id(target_lang))
        else:
            out = model.generate(**inputs)
        translated.extend(tokenizer.decode(t, skip_special_tokens=True) for t in out)

    return translated
