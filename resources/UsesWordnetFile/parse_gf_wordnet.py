import sqlite3
import re
import os

def setup_database(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute('DROP TABLE IF EXISTS synsets')
    cursor.execute('DROP TABLE IF EXISTS functions')
    
    cursor.execute('''
    CREATE TABLE synsets (
        synset_id TEXT PRIMARY KEY,
        pos TEXT,
        definition TEXT
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE functions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fun_name TEXT,
        category TEXT,
        synset_id TEXT,
        eng_lin TEXT,
        spa_lin TEXT,
        FOREIGN KEY (synset_id) REFERENCES synsets(synset_id)
    )
    ''')
    
    cursor.execute('CREATE INDEX idx_fun_name ON functions(fun_name)')
    cursor.execute('CREATE INDEX idx_synset_id ON functions(synset_id)')
    
    conn.commit()
    return conn

def parse_abstract(file_path, conn):
    cursor = conn.cursor()
    print(f"Parsing abstract syntax: {file_path}")
    
    # Regex to match: fun fun_name : category ; -- synset_id definition
    # Example: fun abandon_1_V2 : V2 ; -- 02232813-v	forsake, leave behind; "We abandoned the old car in the empty parking lot"
    pattern = re.compile(r'fun\s+([\w_]+)\s+:\s+([\w_]+)\s+;\s+--\s+([\w-]+)\s+(.*)')
    
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            match = pattern.search(line)
            if match:
                fun_name, category, synset_id, info = match.groups()
                # Split info into definition (everything after the first tab or space)
                # WordNet.gf seems to use tabs or spaces after synset_id
                parts = info.split('\t', 1)
                definition = parts[0] if len(parts) == 1 else parts[1]
                
                # Extract POS from synset_id (e.g., 02232813-v -> v)
                pos = synset_id.split('-')[-1] if '-' in synset_id else ''
                
                cursor.execute('INSERT OR IGNORE INTO synsets (synset_id, pos, definition) VALUES (?, ?, ?)',
                               (synset_id, pos, definition))
                cursor.execute('INSERT INTO functions (fun_name, category, synset_id) VALUES (?, ?, ?)',
                               (fun_name, category, synset_id))
    
    conn.commit()

def parse_concrete(file_path, lang, conn):
    cursor = conn.cursor()
    print(f"Parsing {lang} concrete syntax: {file_path}")
    
    # Regex to match: lin fun_name = linearization ;
    # Example: lin abandon_1_V2 = mkV2 (mkV "abandonar") ;
    pattern = re.compile(r'lin\s+([\w_]+)\s+=\s+(.*)\s*;')
    
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            match = pattern.search(line)
            if match:
                fun_name, linearization = match.groups()
                linearization = linearization.strip()
                
                if lang == 'eng':
                    cursor.execute('UPDATE functions SET eng_lin = ? WHERE fun_name = ?', (linearization, fun_name))
                elif lang == 'spa':
                    cursor.execute('UPDATE functions SET spa_lin = ? WHERE fun_name = ?', (linearization, fun_name))
    
    conn.commit()

if __name__ == "__main__":
    DB_PATH = "gf_wordnet.db"
    GF_WN_DIR = "/home/ubuntu/gf-wordnet"
    
    connection = setup_database(DB_PATH)
    try:
        parse_abstract(os.path.join(GF_WN_DIR, "WordNet.gf"), connection)
        parse_concrete(os.path.join(GF_WN_DIR, "WordNetEng.gf"), 'eng', connection)
        parse_concrete(os.path.join(GF_WN_DIR, "WordNetSpa.gf"), 'spa', connection)
        
        # Verification
        cursor = connection.cursor()
        cursor.execute('SELECT COUNT(*) FROM functions WHERE eng_lin IS NOT NULL AND spa_lin IS NOT NULL')
        count = cursor.fetchone()[0]
        print(f"Total functions with both English and Spanish linearizations: {count}")
        
    finally:
        connection.close()
