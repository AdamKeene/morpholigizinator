"""
Lesson generator demonstration script.

Runs build_lesson on sample documents and prints a formatted view of each
word entry: translations, alternate senses, generated example sentences,
and source examples from the document.

Each run demonstrates a single source→target pair, matching how the web
layer calls build_lesson() — one pair per user session.

Run from project root:
    python test.py

For the automated test suite, use pytest:
    pytest                         # unit tests only (fast, no resources needed)
    pytest -m "not slow"           # unit + integration (needs Parse.pgf)
    pytest -m slow                 # full end-to-end pipeline tests (minutes)
"""

from translator import build_lesson

_EV_TEXT_EN = open("resources/sample_document_en.txt").read()

EV_VOCAB_EN = {
    "battery":    "N",
    "charge":     "V2",
    "run":        "V",
    "fast":       "A",
    "electric":   "A",
    "vehicle":    "N",
    "cell":       "N",
}


def _fmt_translations(translations, langs):
    return "  ".join(f"{l}: {translations.get(l, '—')}" for l in langs)


def print_entry(entry, langs):
    word = entry["word"]
    fn = entry["gf_function"] or "(not in WordNet)"
    print(f"\n{'─' * 60}")
    print(f"  {word!r}  [{entry['gf_cat']}]  →  {fn}")
    print(f"  in_wordnet: {entry['in_wordnet']}  |  source_count: {entry['source_count']}")

    if entry["translations"]:
        print(f"  translations:  {_fmt_translations(entry['translations'], langs)}")

    if entry["alternates"]:
        shown = entry["alternates"][:4]
        print(f"  alternates ({len(entry['alternates'])}, showing {len(shown)}):")
        for alt in shown:
            t = _fmt_translations(alt["translations"], langs)
            src_note = f"  [in source ×{alt['source_count']}]" if alt["source_count"] else ""
            print(f"    {alt['gf_function']}: {t}{src_note}")

    if entry["sentences"]:
        shown = entry["sentences"][:5]
        print(f"  sentences ({len(entry['sentences'])}, showing {len(shown)}):")
        for sent in shown:
            t = _fmt_translations(sent, langs)
            print(f"    [{sent['label']}]  {t}")

    if entry["source_examples"]:
        print(f"  source examples ({len(entry['source_examples'])}):")
        for ex in entry["source_examples"]:
            print(f"    {ex['text']}")


def run_lesson(label, vocab, text, source_lang, target_lang):
    langs = [source_lang, target_lang]
    print(f"\n{'=' * 60}")
    print(f"  {label}")
    print(f"  vocab: {list(vocab.keys())}")
    print(f"  {source_lang} → {target_lang}")
    print("=" * 60)
    entries = build_lesson(vocab, text, source_lang, [target_lang])
    for entry in entries:
        print_entry(entry, langs)


run_lesson(
    label="EV domain  (en → de)",
    vocab=EV_VOCAB_EN,
    text=_EV_TEXT_EN,
    source_lang="en",
    target_lang="de",
)
