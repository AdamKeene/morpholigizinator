import sqlite3
import nltk
from nltk.corpus import wordnet as wn

def setup_database(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create tables
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS synsets (
        synset_id TEXT PRIMARY KEY,
        pos TEXT,
        definition TEXT
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS lemmas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        synset_id TEXT,
        lang TEXT,
        lemma TEXT,
        FOREIGN KEY (synset_id) REFERENCES synsets(synset_id)
    )
    ''')
    
    # Create indexes for performance
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_lemmas_synset ON lemmas(synset_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_lemmas_lang_lemma ON lemmas(lang, lemma)')
    
    conn.commit()
    return conn

def extract_data(conn):
    cursor = conn.cursor()
    
    print("Starting extraction...")
    
    # Iterate through all synsets in WordNet
    all_synsets = list(wn.all_synsets())
    total = len(all_synsets)
    
    for i, synset in enumerate(all_synsets):
        synset_id = synset.name()
        pos = synset.pos()
        definition = synset.definition()
        
        # Insert synset
        cursor.execute('INSERT OR IGNORE INTO synsets (synset_id, pos, definition) VALUES (?, ?, ?)',
                       (synset_id, pos, definition))
        
        # Extract English lemmas
        for lemma in synset.lemmas():
            cursor.execute('INSERT INTO lemmas (synset_id, lang, lemma) VALUES (?, ?, ?)',
                           (synset_id, 'eng', lemma.name()))
            
        # Extract Spanish lemmas using Open Multilingual WordNet
        for lemma_name in synset.lemma_names('spa'):
            cursor.execute('INSERT INTO lemmas (synset_id, lang, lemma) VALUES (?, ?, ?)',
                           (synset_id, 'spa', lemma_name))
            
        if i % 5000 == 0:
            print(f"Processed {i}/{total} synsets...")
            conn.commit()
            
    conn.commit()
    print("Extraction complete.")

if __name__ == "__main__":
    DB_PATH = "wordnet_translation.db"
    connection = setup_database(DB_PATH)
    try:
        extract_data(connection)
    finally:
        connection.close()
