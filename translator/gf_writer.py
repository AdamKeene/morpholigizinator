import os
import shutil
import subprocess
from pathlib import Path

from .config import LANG_CONFIG, GF_WORDNET_DIR, GF_WORDNET_BUILD_GFO

# Pre-compiled .gfo files that need to be staged into the gf-wordnet root before
# compilation. Languages with empty lists are already in place.
_PRECOMPILED_GFO = {
    "Eng": [],
    "Spa": [],
    "Ger": ["ParseGer.gfo", "WordNetGer.gfo", "ParseExtendGer.gfo"],
    "Jpn": [],
}


def stage_gfo_files(suffix):
    """Copy pre-compiled gfo files for a language into the gf-wordnet root."""
    for fname in _PRECOMPILED_GFO.get(suffix, []):
        src = Path(GF_WORDNET_BUILD_GFO) / fname
        dst = Path(GF_WORDNET_DIR) / fname
        if src.exists() and not dst.exists():
            shutil.copy2(src, dst)
            print(f"  Staged {fname} → gf-wordnet root")


def generate_gf_files(found_entries, generated_entries, target_langs, output_dir, module_name):
    """
    Write abstract DomainLexicon.gf and one concrete per target language.

    Only generated_entries (words NOT in WordNet) are declared here.
    found_entries are already in the WordNet abstract and available via
    Parse{Lang} — redeclaring them would cause a conflict at link time.
    """
    print(f"5. Writing GF files to {output_dir}/...")
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    if found_entries:
        print(f"  WordNet entries ({len(found_entries)}) available via Parse{{Lang}} — not redeclared.")

    seen = {}
    for e in generated_entries:
        seen.setdefault(e["fun_name"], e)
    unique = sorted(seen.values(), key=lambda e: e["fun_name"])

    if not unique:
        print("  No entries to write.")
        return

    abstract_lines = [f"abstract {module_name} = Cat ** {{", "  fun"]
    for e in unique:
        abstract_lines.append(f"    {e['fun_name']} : {e['category']} ;")
    abstract_lines.append("}")
    abstract_path = Path(output_dir) / f"{module_name}.gf"
    abstract_path.write_text("\n".join(abstract_lines) + "\n", encoding="utf-8")
    print(f"  {abstract_path.name}: {len(unique)} functions")

    for lang in target_langs:
        cfg = LANG_CONFIG.get(lang)
        if not cfg:
            print(f"  WARNING: no config for '{lang}', skipping")
            continue

        suffix = cfg["gf_suffix"]
        concrete_name = f"{module_name}{suffix}"
        lines = [
            f"concrete {concrete_name} of {module_name} = {cfg['gf_cat_module']} ** open {cfg['gf_open']} in {{",
            "  lin",
        ]
        covered = 0
        for e in unique:
            lin = e["lins"].get(lang)
            if lin:
                lines.append(f"    {e['fun_name']} = {lin} ;")
                covered += 1
            else:
                lines.append(f"    {e['fun_name']} = variants {{}} ;")
        lines.append("}")

        out_path = Path(output_dir) / f"{concrete_name}.gf"
        out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"  {out_path.name}: {covered}/{len(unique)} entries translated")


def generate_translator_files(target_langs, output_dir, module_name):
    """Write DomainTranslator.gf (abstract) and one concrete per target language."""
    print("6. Writing DomainTranslator GF files...")
    translator_name = "DomainTranslator"

    abstract_path = Path(output_dir) / f"{translator_name}.gf"
    abstract_path.write_text(
        f"abstract {translator_name} = Parse, {module_name} ** {{}}\n",
        encoding="utf-8",
    )
    print(f"  {abstract_path.name}")

    for lang in target_langs:
        cfg = LANG_CONFIG.get(lang)
        if not cfg:
            continue
        suffix = cfg["gf_suffix"]
        concrete_name = f"{translator_name}{suffix}"
        concrete_path = Path(output_dir) / f"{concrete_name}.gf"
        concrete_path.write_text(
            f"concrete {concrete_name} of {translator_name} = "
            f"Parse{suffix}, {module_name}{suffix} ** {{}}\n",
            encoding="utf-8",
        )
        print(f"  {concrete_path.name}")


def compile_grammar(target_langs, output_dir):
    """
    Compile DomainTranslator*.gf into DomainTranslator.pgf using GF's
    interactive mode. --make can't use Parse.pgf as a source dependency, but
    interactive `import` can load it as a precompiled module first, then
    compile the domain files against it.
    """
    print("7. Compiling DomainTranslator.pgf...")
    translator_name = "DomainTranslator"
    out = Path(output_dir)
    pgf_out = out / f"{translator_name}.pgf"

    for lang in target_langs:
        cfg = LANG_CONFIG.get(lang)
        if cfg:
            stage_gfo_files(cfg["gf_suffix"])

    # Collect all .gf files to compile: DomainLexicon + DomainTranslator concretes
    suffixes = [LANG_CONFIG[lang]["gf_suffix"] for lang in target_langs if LANG_CONFIG.get(lang)]
    gf_files = []
    for name in [f"DomainLexicon{s}" for s in suffixes] + [f"{translator_name}{s}" for s in suffixes]:
        f = out / f"{name}.gf"
        if f.exists():
            gf_files.append(str(f))

    # Also include the abstracts
    for abstract in [str(out / "DomainLexicon.gf"), str(out / f"{translator_name}.gf")]:
        if Path(abstract).exists() and abstract not in gf_files:
            gf_files.insert(0, abstract)

    if not gf_files:
        print("  No GF files found, skipping compile.")
        return

    # GF interactive mode: import Parse.pgf first (makes Parse/* available),
    # then import domain files, then write the compiled PGF.
    gf_commands = "\n".join([
        "import Parse.pgf",
        f"import {' '.join(gf_files)}",
        f"write pgf {pgf_out}",
        "quit",
    ]) + "\n"

    print(f"  gf interactive [{', '.join(target_langs)}]")
    try:
        result = subprocess.run(
            ["gf"], input=gf_commands, capture_output=True, text=True
        )
        if result.returncode != 0 or not pgf_out.exists():
            print(f"  Compile FAILED (exit {result.returncode})")
            for line in (result.stderr + result.stdout).splitlines():
                print(f"    {line}")
        else:
            print(f"  OK → {pgf_out}")
    except FileNotFoundError:
        print("  'gf' binary not found — is GF installed and on PATH?")
