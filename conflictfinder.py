import re
from pathlib import Path

def extract_abs_wn(gf_file_path):
    pattern = re.compile(
        r'^\s*fun\s*'               # 'fun' keyword
        r'(?:--[^\n]*\n\s*)*'       # Skip inline comments after 'fun'
        r'([a-zA-Z_][\w]*)\s*:'      # Capture function name
        r'[^;]*;'                   # Match type declaration
        r'(?:\s*--[^\n]*)?'         # Optional trailing comment
        ,
        re.MULTILINE | re.VERBOSE
    )
    with open(gf_file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    return set(pattern.findall(content))

def extract_abs_rgl(gf_file_path):
    with open(gf_file_path, 'r', encoding='utf-8') as f:
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

def extract_conc_wn(gf_file_path):
    pass
def extract_conc_rgl(gf_file_path):
    pass

def find_shared_functions(grammar1_path, grammar2_path):
    """Find function names present in both grammars."""
    funcs1 = extract_abs_rgl(grammar1_path)
    funcs2 = extract_abs_wn(grammar2_path)
    print(len(funcs1), len(funcs2))
    print(f"unique: {funcs1 - funcs2}")
    return funcs1 & funcs2  # Set intersection

def find_conflicts(rgl_directory, wordnet_file):
    all_conflicts = set()
    for gf_file in Path(rgl_directory).glob("*.gf"):
        print(f"Checking {gf_file.name}...")
        conflicts = find_shared_functions(gf_file, wordnet_file)
        if conflicts:
            all_conflicts.update(conflicts)
            print(f"⚠️ {len(conflicts)} naming conflicts found in {gf_file.name}:")
            for i, name in enumerate(sorted(conflicts), 1):
                print(f"{i}. {name}")
        else:
            print(f"✅ No naming conflicts detected in {gf_file.name}.")
        print("-" * 40)
    print(f"Total naming conflicts found: {len(all_conflicts)}")
    print(",\n".join(sorted(all_conflicts)))

find_conflicts("/usr/share/gf-3.11/gf-rgl/src/english", "/usr/share/gf-3.11/gf-wordnet/WordNetEng.gf")