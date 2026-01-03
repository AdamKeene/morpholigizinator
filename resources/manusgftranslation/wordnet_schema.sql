-- Schema for WordNet Synsets and Lemmas (English and Spanish)

CREATE TABLE IF NOT EXISTS synsets (
    synset_id TEXT PRIMARY KEY, -- e.g., 'dog.n.01'
    pos TEXT,                   -- Part of Speech: n, v, a, r
    definition TEXT             -- English definition
);

CREATE TABLE IF NOT EXISTS lemmas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    synset_id TEXT,
    lang TEXT,                  -- 'eng' or 'spa'
    lemma TEXT,                 -- The actual word/phrase
    FOREIGN KEY (synset_id) REFERENCES synsets(synset_id)
);

CREATE INDEX IF NOT EXISTS idx_lemmas_synset ON lemmas(synset_id);
CREATE INDEX IF NOT EXISTS idx_lemmas_lang_lemma ON lemmas(lang, lemma);
