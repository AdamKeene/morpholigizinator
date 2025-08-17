import pgf
from pathlib import Path
''' 
export GF_LIB_PATH="/usr/share/gf-3.11/gf-rgl/src/abstract:/usr/share/gf-3.11/gf-wordnet:$GF_LIB_PATH"
'''

def get_funcs(path):
    grammar = pgf.readPGF(path)
    return grammar.functions

def find_dependencies(path):
    dependencies = []
    for gf_file in Path(path).glob("*.gf"):
        with open(gf_file, 'r') as f:
            content = f.read()
            for line in content.splitlines():
                if line.strip().startswith('concrete'):
                    objs = line.split()
                    for i, item in enumerate(objs):
                        if item == '**':
                            if i+1 < len(objs):
                                obj = objs[i + 1]
                                dependencies.append(obj.strip(','))
                                while obj.endswith(',') and i + 1 < len(objs):
                                    i += 1
                                    dependencies.append(objs[i + 1].strip(','))
    dependencies = sorted(set(dependencies))
    if 'open' in dependencies:
        dependencies.remove('open')
    return '.gf '.join(dependencies) + '.gf'

def find_conflicts(paths):
    all_funcs = set(get_funcs(paths[0]))
    conflicts = set()
    for path in paths[1:]:
        funcs = set(get_funcs(path))
        conflicts.update(funcs & all_funcs)
        all_funcs.update(funcs)
    if conflicts:
        print(f'{len(conflicts)} conflicts:')
        print(',\n'.join(sorted(conflicts)))

# print(find_dependencies("/usr/share/gf-3.11/gf-rgl/src/spanish"))
find_conflicts(["/home/adam/Documents/pgf-code/pgfs/AllSpaAbs.pgf", "/home/adam/Documents/pgf-code/pgfs/WordNetSpa.pgf", "/home/adam/Documents/pgf-code/pgfs/Romance.pgf"])