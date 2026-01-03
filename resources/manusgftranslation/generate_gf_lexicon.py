import sqlite3
import re

def sanitize_gf_id(text):
    sanitized = re.sub(r'[^a-zA-Z0-9_]', '_', text)
    if not sanitized[0].isalpha():
        sanitized = 'w_' + sanitized
    return sanitized

def get_gf_category(pos):
    mapping = {
        'n': 'N',
        'v': 'V',
        'a': 'A',
        's': 'A',
        'r': 'Adv'
    }
    return mapping.get(pos, 'N')

def get_gf_constructor(pos, lemma, lang):
    if pos == 'n':
        return 'mkN'
    elif pos == 'v':
        return 'mkV'
    elif pos in ['a', 's']:
        return 'mkA'
    elif pos == 'r':
        return 'mkAdv'
    return 'mkN'

def generate_gf_files(db_path, limit=1000):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Filter out Spanish verbs that don't end in ar/er/ir to avoid GF compiler errors
    query = '''
    SELECT s.synset_id, s.pos, e.lemma, sp.lemma
    FROM synsets s
    JOIN lemmas e ON s.synset_id = e.synset_id AND e.lang = 'eng'
    JOIN lemmas sp ON s.synset_id = sp.synset_id AND sp.lang = 'spa'
    WHERE NOT (s.pos = 'v' AND NOT (sp.lemma LIKE '%ar' OR sp.lemma LIKE '%er' OR sp.lemma LIKE '%ir'))
    GROUP BY s.synset_id
    LIMIT ?
    '''
    
    cursor.execute(query, (limit,))
    results = cursor.fetchall()
    
    abstract_entries = []
    english_entries = []
    spanish_entries = []
    
    for synset_id, pos, eng_lemma, spa_lemma in results:
        gf_id = sanitize_gf_id(synset_id)
        cat = get_gf_category(pos)
        
        eng_lemma_clean = eng_lemma.replace('_', ' ').replace('"', '\\"')
        spa_lemma_clean = spa_lemma.replace('_', ' ').replace('"', '\\"')
        
        abstract_entries.append(f"    {gf_id} : {cat} ;")
        
        eng_cons = get_gf_constructor(pos, eng_lemma_clean, 'eng')
        spa_cons = get_gf_constructor(pos, spa_lemma_clean, 'spa')
        
        english_entries.append(f"    {gf_id} = {eng_cons} \"{eng_lemma_clean}\" ;")
        spanish_entries.append(f"    {gf_id} = {spa_cons} \"{spa_lemma_clean}\" ;")
        
    # Write Abstract file
    with open('WordNetLexicon.gf', 'w') as f:
        f.write("abstract WordNetLexicon = {\n")
        f.write("  cat\n")
        f.write("    N ; V ; A ; Adv ;\n")
        f.write("  fun\n")
        f.write("\n".join(abstract_entries))
        f.write("\n}\n")
        
    # Write English Concrete file
    # Using 'open' instead of inheritance to avoid linking issues with complex RGL structures
    with open('WordNetLexiconEng.gf', 'w') as f:
        f.write("concrete WordNetLexiconEng of WordNetLexicon = open ParadigmsEng, CatEng in {\n")
        f.write("  lincat\n")
        f.write("    N = CatEng.N ;\n")
        f.write("    V = CatEng.V ;\n")
        f.write("    A = CatEng.A ;\n")
        f.write("    Adv = CatEng.Adv ;\n")
        f.write("  lin\n")
        f.write("\n".join(english_entries))
        f.write("\n}\n")
        
    # Write Spanish Concrete file
    with open('WordNetLexiconSpa.gf', 'w') as f:
        f.write("concrete WordNetLexiconSpa of WordNetLexicon = open ParadigmsSpa, CatSpa in {\n")
        f.write("  lincat\n")
        f.write("    N = CatSpa.N ;\n")
        f.write("    V = CatSpa.V ;\n")
        f.write("    A = CatSpa.A ;\n")
        f.write("    Adv = CatSpa.Adv ;\n")
        f.write("  lin\n")
        f.write("\n".join(spanish_entries))
        f.write("\n}\n")
        
    print(f"Generated GF files with {len(results)} entries.")
    conn.close()

if __name__ == "__main__":
    generate_gf_files('wordnet_translation.db', limit=500)
