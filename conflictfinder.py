import re
from pathlib import Path

def get_abs_wn(path):
    pattern = re.compile(
        r'^\s*fun\s*'               # 'fun' keyword
        r'(?:--[^\n]*\n\s*)*'       # Skip inline comments after 'fun'
        r'([a-zA-Z_][\w]*)\s*:'      # Capture function name
        r'[^;]*;'                   # Match type declaration
        r'(?:\s*--[^\n]*)?'         # Optional trailing comment
        ,
        re.MULTILINE | re.VERBOSE
    )
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    return set(pattern.findall(content))

def get_abs_rgl(path):
    with open(path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    functions = set()
    in_fun_section = False

    for line in lines:
        if line.strip() == 'fun':
            in_fun_section = True
            continue
        if in_fun_section:
            line = line.split('--')[0].strip()
            if not line:
                continue
            if match := re.match(r'([a-zA-Z]\w*)\s*:', line):
                functions.add(match.group(1))
    return functions

def get_conc_wn(path):
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    pattern = re.compile(
        r'^\s*lin\s+([a-z][a-zA-Z0-9_]*(?:_[A-Z][a-zA-Z]*)?)\s*(?==)',
        re.MULTILINE
    )
    
    matches = pattern.findall(content)
    return set(matches)

def get_conc_rgl(path):
    pattern = re.compile(
        r'^\s*lin\s+([A-Z][a-zA-Z0-9_]*)'  # Match capitalized function names
        r'(?:\s*=\s*\{|\s*$)'              # Handle both '= {' and line endings
        , re.MULTILINE
    )
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    functions = set(pattern.findall(content))
    return functions

def find_shared_functions(grammar1_path, grammar2_path, gtype):
    if gtype == "abs":
        funcs1 = get_abs_rgl(grammar1_path)
        funcs2 = get_abs_wn(grammar2_path)
    elif gtype == "conc":
        funcs1 = get_conc_rgl(grammar1_path)
        funcs2 = get_conc_wn(grammar2_path)
    print(len(funcs1), len(funcs2))
    print(f"unique: {len(funcs1 - funcs2)}")
    return funcs1 & funcs2

def find_conflicts(rgl_directory, wordnet_file, gtype):
    all_conflicts = set()
    if gtype == "abs":
        abs_wn = get_abs_wn(wordnet_file)
    elif gtype == "conc":
        conc_wn = get_conc_wn(wordnet_file)
    for rgl_file in Path(rgl_directory).glob("*.gf"):
        print(f"Checking {rgl_file.name}...")
        if gtype == "abs":
            funcs1 = get_abs_rgl(rgl_file)
            funcs2 = abs_wn
        elif gtype == "conc":
            funcs1 = get_conc_rgl(rgl_file)
            funcs2 = conc_wn
        print(len(funcs1), len(funcs2))
        print(f"unique: {len(funcs1 - funcs2)}")
        conflicts = funcs1 & funcs2

        if conflicts:
            all_conflicts.update(conflicts)
            print(f"⚠️ {len(conflicts)} naming conflicts found in {rgl_file.name}:")
            for i, name in enumerate(sorted(conflicts), 1):
                print(f"{i}. {name}")
        else:
            print(f"✅ No naming conflicts detected in {rgl_file.name}.")
        print("-" * 40)
    print(f"Total naming conflicts found: {len(all_conflicts)}")
    print(",\n".join(sorted(all_conflicts)))

find_conflicts("/usr/share/gf-3.11/gf-rgl/src/english", "/usr/share/gf-3.11/gf-wordnet/WordNetEng.gf")