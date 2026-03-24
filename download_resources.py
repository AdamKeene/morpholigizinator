"""
Download large resource files that can't be stored in git.

Usage:
    python download_resources.py              # download everything
    python download_resources.py --langs en es  # specific languages only
    python download_resources.py --skip-fasttext # skip fastText vectors
"""

import argparse
import gzip
import os
import shutil
import subprocess
import sys
from pathlib import Path

RESOURCES_DIR = Path("resources")

# fastText Common Crawl vectors (300-dim, ~4.3GB each uncompressed)
FASTTEXT_BASE = "https://dl.fbaipublicfiles.com/fasttext/vectors-crawl"
FASTTEXT_LANGS = {
    "en": "cc.en.300.vec",
    "es": "cc.es.300.vec",
    "de": "cc.de.300.vec",
    "ja": "cc.ja.300.vec",
}

# spaCy models per language
SPACY_MODELS = {
    "en": "en_core_web_sm",
    "es": "es_core_news_sm",
    "de": "de_core_news_sm",
    "ja": "ja_core_news_sm",
}


def download_file(url, dest: Path, desc=""):
    """Stream-download a file with a simple progress indicator."""
    import urllib.request

    desc = desc or dest.name
    print(f"  Downloading {desc}...")
    print(f"    {url}")

    def reporthook(count, block_size, total_size):
        if total_size > 0:
            pct = min(100, count * block_size * 100 // total_size)
            print(f"\r    {pct}%", end="", flush=True)

    urllib.request.urlretrieve(url, dest, reporthook=reporthook)
    print()  # newline after progress


def download_fasttext(langs):
    RESOURCES_DIR.mkdir(exist_ok=True)
    for lang in langs:
        if lang not in FASTTEXT_LANGS:
            print(f"  No fastText config for '{lang}', skipping.")
            continue
        vec_name = FASTTEXT_LANGS[lang]
        vec_path = RESOURCES_DIR / vec_name
        if vec_path.exists():
            print(f"  {vec_name} already exists, skipping.")
            continue

        gz_path = vec_path.with_suffix(".vec.gz")
        url = f"{FASTTEXT_BASE}/{vec_name}.gz"
        download_file(url, gz_path, desc=f"{vec_name}.gz (~1.2GB compressed)")

        print(f"  Decompressing {gz_path.name} (~4.3GB)...")
        with gzip.open(gz_path, "rb") as f_in, open(vec_path, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
        gz_path.unlink()
        print(f"  Done → {vec_path}")


def download_spacy_models(langs):
    for lang in langs:
        model = SPACY_MODELS.get(lang)
        if not model:
            print(f"  No spaCy model configured for '{lang}', skipping.")
            continue
        print(f"  Installing spaCy model: {model}")
        subprocess.run(
            [sys.executable, "-m", "spacy", "download", model],
            check=True,
        )


def main():
    parser = argparse.ArgumentParser(description="Download project resources")
    parser.add_argument(
        "--langs",
        nargs="+",
        default=list(FASTTEXT_LANGS.keys()),
        metavar="LANG",
        help="Language codes to download resources for (default: all)",
    )
    parser.add_argument(
        "--skip-fasttext",
        action="store_true",
        help="Skip fastText vector download",
    )
    parser.add_argument(
        "--skip-spacy",
        action="store_true",
        help="Skip spaCy model download",
    )
    args = parser.parse_args()

    print(f"Languages: {args.langs}\n")

    if not args.skip_fasttext:
        print("=== fastText vectors ===")
        download_fasttext(args.langs)
        print()

    if not args.skip_spacy:
        print("=== spaCy models ===")
        download_spacy_models(args.langs)
        print()

    print("Done.")
    print("\nNext steps:")
    print("  1. Install GF 3.11 from https://www.grammaticalframework.org/download/")
    print("  2. Run: python multilingual_pipeline.py")


if __name__ == "__main__":
    main()
