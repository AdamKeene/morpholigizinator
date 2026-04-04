import glob
import os
import subprocess
from pathlib import Path

from .config import LANG_CONFIG


def _find_gf_rgl_path():
    """
    Locate the GF Resource Grammar Library (RGL) compiled module directory.

    The RGL provides the paradigm modules (ParadigmsGer, CatGer, Prelude, ...)
    needed to compile DomainLexicon concrete files. It is distributed separately
    from the GF binary (e.g. gf-rgl release archive) and its location varies.

    Search order:
    1. GF_LIB_PATH environment variable (standard GF convention)
    2. ~/gf-rgl/*/alltenses   (manually installed release archive)
    3. Common system paths

    Returns the path to the 'alltenses' subdirectory, or None if not found.
    """
    candidates = []

    env_lib = os.environ.get("GF_LIB_PATH")
    if env_lib:
        candidates.append(env_lib)
        candidates.append(os.path.join(env_lib, "alltenses"))

    home = os.path.expanduser("~")
    candidates += glob.glob(os.path.join(home, "gf-rgl", "*", "alltenses"))
    candidates += glob.glob("/usr/share/gf-rgl/*/alltenses")
    candidates += glob.glob("/usr/local/share/gf-rgl/*/alltenses")

    for path in candidates:
        if os.path.isfile(os.path.join(path, "Prelude.gfo")):
            return path
    return None


def generate_gf_files(entries, target_langs, output_dir, module_name):
    """
    Write abstract DomainLexicon.gf and one concrete per target language.

    Only entries for words NOT in the GF WordNet (Wiktionary hits and genuine
    NMT-generated words) are declared here. WordNet words are available via
    Parse{Lang} at runtime and must NOT be redeclared — doing so would cause
    a duplicate-function conflict at GF link time.

    Each concrete file opens the appropriate RGL modules for its language so
    that paradigm calls like mkN, mkV2 etc. resolve correctly at compile time.
    """
    print(f"  Writing GF files to {output_dir}/...")
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Deduplicate by fun_name (same word may appear via multiple lookup paths)
    seen = {}
    for e in entries:
        seen.setdefault(e["fun_name"], e)
    unique = sorted(seen.values(), key=lambda e: e["fun_name"])

    if not unique:
        print("  No entries to write.")
        return

    # Abstract: declares each new word with its GF category (N, V2, A, …)
    abstract_lines = [f"abstract {module_name} = Cat ** {{", "  fun"]
    for e in unique:
        abstract_lines.append(f"    {e['fun_name']} : {e['category']} ;")
    abstract_lines.append("}")
    abstract_path = Path(output_dir) / f"{module_name}.gf"
    abstract_path.write_text("\n".join(abstract_lines) + "\n", encoding="utf-8")
    print(f"  {abstract_path.name}: {len(unique)} functions")

    # Concretes: one per language, each with lin expressions from the entry dict.
    # Missing translations use `variants {}` (GF's "no realisation" placeholder),
    # which is valid syntax but will cause a parse failure at runtime for that word.
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
    """
    Write DomainTranslator.gf (abstract) and one concrete per target language.

    DomainTranslator extends both Parse (pre-compiled GF WordNet grammar, ~100k
    words) and DomainLexicon (new domain-specific words). The abstract simply
    re-exports both; the concretes combine Parse{Lang} with DomainLexicon{Lang}.
    """
    print("6. Writing DomainTranslator GF files...")
    translator_name = "DomainTranslator"

    abstract_path = Path(output_dir) / f"{translator_name}.gf"
    # Set startcat = Phr to match Parse.pgf's convention.
    # Without this, DomainLexicon inherits startcat = S (from Cat), which
    # only accepts complete sentences. Parse.pgf uses Phr, which accepts
    # sentences, noun phrases, and bare words — required for Japanese input
    # where single nouns/compounds are valid translation units.
    abstract_path.write_text(
        f"abstract {translator_name} = Parse, {module_name} ** {{\n"
        f"  flags startcat = Phr ;\n"
        f"}}\n",
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
    interactive mode.

    Why interactive mode instead of `gf --make`:
        `gf --make` resolves imports by searching for source .gf files,
        so it cannot use Parse.pgf (a pre-compiled binary) as a dependency.
        Interactive mode can `import` a .pgf directly, making all its
        functions available before the domain files are compiled against it.

    Command sequence sent to GF stdin:
        import Parse.pgf          -- loads pre-compiled WordNet grammar
        import DomainLexicon*.gf DomainTranslator*.gf  -- compiles domain files
        write pgf DomainTranslator.pgf  -- outputs merged binary
        quit
    """
    print("7. Compiling DomainTranslator.pgf...")
    translator_name = "DomainTranslator"
    out = Path(output_dir)
    pgf_out = out / f"{translator_name}.pgf"

    # Collect .gf files to compile: concretes first, then abstracts prepended
    suffixes = [LANG_CONFIG[lang]["gf_suffix"] for lang in target_langs if LANG_CONFIG.get(lang)]
    gf_files = []
    for name in [f"DomainLexicon{s}" for s in suffixes] + [f"{translator_name}{s}" for s in suffixes]:
        f = out / f"{name}.gf"
        if f.exists():
            gf_files.append(str(f))

    for abstract in [str(out / "DomainLexicon.gf"), str(out / f"{translator_name}.gf")]:
        if Path(abstract).exists() and abstract not in gf_files:
            gf_files.insert(0, abstract)

    if not gf_files:
        print("  No GF files found, skipping compile.")
        return

    # Cache check: if the .pgf already exists and all .gf source files have
    # the same content as when it was written, skip recompilation entirely.
    # GF compilation takes ~1-2 min; skipping it when nothing changed is a
    # significant speedup for repeated runs on the same document.
    cache_file = out / ".gf_cache_hash"
    import hashlib
    hasher = hashlib.md5()
    for gf in sorted(gf_files):
        try:
            hasher.update(Path(gf).read_bytes())
        except OSError:
            pass
    hasher.update("|".join(sorted(target_langs)).encode())
    current_hash = hasher.hexdigest()
    if pgf_out.exists() and cache_file.exists():
        if cache_file.read_text().strip() == current_hash:
            print(f"  Cache hit — reusing {pgf_out}")
            return

    # Delete stale .gfo files from previous runs. GF uses cached .gfo files when
    # the corresponding .gf source hasn't changed, but the abstract (DomainLexicon.gf)
    # changes every run. Stale concretes that predate the current abstract cause silent
    # link failures (the concrete is loaded from .gfo but mismatches the new abstract).
    for gfo in out.glob("*.gfo"):
        gfo.unlink(missing_ok=True)

    # `write pgf` was the old GF interactive command; current GF (3.12+) uses
    # `pg -pgf -file=...` to write the loaded grammar as a binary .pgf.
    gf_commands = "\n".join([
        "import Parse.pgf",
        f"import {' '.join(gf_files)}",
        f"pg -pgf -file={pgf_out}",
        "quit",
    ]) + "\n"

    rgl_path = _find_gf_rgl_path()
    cmd = ["gf", "--optimize-pgf"]
    if rgl_path:
        # RGL compiled modules (CatGer, ParadigmsGer, Prelude, etc.)
        cmd += ["-i", rgl_path]
        # gf-wordnet source files (Parse.gf, ParseGer.gf, ParseExtend*.gf, WordNet*.gf)
        cmd += ["-i", "resources/gf-wordnet"]
    else:
        print("  WARNING: GF RGL not found — concrete files may fail to compile.")
        print("    Set GF_LIB_PATH or install the gf-rgl release archive to ~/gf-rgl/")

    # Delete any stale .pgf before compiling so a failed compile is detectable.
    pgf_out.unlink(missing_ok=True)

    print(f"  gf interactive [{', '.join(target_langs)}]")
    try:
        result = subprocess.run(
            cmd, input=gf_commands, capture_output=True, text=True
        )
        # Verify the written pgf actually contains DomainTranslator concretes
        # (a failed compile may still write a stale or Parse-only pgf).
        # Verify success by checking GF's own output: after a successful
        # compile, GF prints "Languages: DomainTranslator<Suffix> ..."
        # This is more reliable than re-reading the binary pgf immediately
        # after it's written (large files may not be fully flushed yet).
        expected = f"DomainTranslator{LANG_CONFIG[target_langs[0]]['gf_suffix']}"
        gf_output = result.stderr + result.stdout
        ok = expected in gf_output and pgf_out.exists()
        if not ok:
            reason = "pgf not written" if not pgf_out.exists() else "expected language not in GF output"
            print(f"  Compile FAILED ({reason})")
            for line in gf_output.splitlines():
                if line.strip():
                    print(f"    {line}")
        else:
            print(f"  OK → {pgf_out}")
            cache_file.write_text(current_hash)
    except FileNotFoundError:
        print("  'gf' binary not found — is GF installed and on PATH?")
