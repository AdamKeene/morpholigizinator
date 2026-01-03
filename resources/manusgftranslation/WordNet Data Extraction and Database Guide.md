# WordNet Data Extraction and Database Guide

This document explains the process of extracting WordNet data, including the Open Multilingual WordNet (OMW) for Spanish, into a structured SQLite database. This database is designed to serve as the lexicon source for the next phase of the Grammatical Framework (GF) translation system development.

## 1. Database Choice and Design Rationale

The choice of **SQLite** for the database is based on its suitability for this project's current needs. SQLite is a file-based, serverless database, making it highly portable and easy to integrate into the development environment without requiring a separate database server.

The database schema is designed to directly model the core concepts of WordNet: **Synsets** and **Lemmas**.

### 1.1. Database Schema (`wordnet_translation.db`)

The database consists of two main tables: `synsets` and `lemmas`.

| Table | Column | Data Type | Description |
| --- | --- | --- | --- |
| `synsets` | `synset_id` | `TEXT` (PK) | The unique identifier for a synset (e.g., `dog.n.01`). This is the core concept linking all translations. |
|  | `pos` | `TEXT` | The Part of Speech (e.g., `n` for noun, `v` for verb). |
|  | `definition` | `TEXT` | The English definition  | variants |  | of the synset. |
| `lemmas` | `id` | `INTEGER` (PK) | Auto-incrementing primary key. |
|  | `synset_id` | `TEXT` (FK) | Foreign key linking the lemma back to its corresponding synset. |
|  | `lang` | `TEXT` | The language code of the lemma (`eng` or `spa`). |
|  | `lemma` | `TEXT` | The word or phrase in the specified language. |

This structure ensures that all English and Spanish words are grouped by their shared meaning (the `synset_id`), which is the exact requirement for building a GF lexicon where a single abstract function corresponds to a single meaning.

## 2. Python Extraction Script (`extract_wordnet.py`)

The extraction process is handled by a Python script that leverages the **Natural Language Toolkit (NLTK)**, which provides programmatic access to WordNet and the Open Multilingual WordNet (OMW).

### 2.1. Key Components

1. **`setup_database(db_path)`**: This function initializes the SQLite database, creating the `synsets` and `lemmas` tables and adding indexes to optimize future lookups. The indexes on `lemmas(synset_id)` and `lemmas(lang, lemma)` are crucial for quickly retrieving all words for a given meaning or finding the meaning for a given word.

1. **`extract_data(conn)`**: This is the core logic:
  - It iterates through every **Synset** in the English WordNet using `wn.all_synsets()`.
  - For each synset, it extracts the `synset_id`, Part of Speech (`pos`), and English `definition`, inserting them into the `synsets` table.
  - It then extracts all **English lemmas** associated with that synset using `synset.lemmas()` and inserts them into the `lemmas` table with the language code `eng`.
  - Finally, it extracts the **Spanish lemmas** using the OMW interface via `synset.lemma_names('spa')` and inserts them into the `lemmas` table with the language code `spa`.

### 2.2. Verification

The script successfully extracted the data, resulting in the following counts:

| Language | Total Lemmas |
| --- | --- |
| English (`eng`) | 206,978 |
| Spanish (`spa`) | 57,764 |

A sample of the `lemmas` table confirms the structure:

| id | synset_id | lang | lemma |
| --- | --- | --- | --- |
| 1 | `able.a.01` | `eng` | `able` |
| 2 | `able.a.01` | `spa` | `capaz` |
| 3 | `unable.a.01` | `eng` | `unable` |
| 4 | `unable.a.01` | `spa` | `incapaz` |

## 3. Next Steps: Generating the GF Lexicon

The extracted data is now ready to be used to generate the GF lexicon. The next step will involve creating a Python script that queries this database and outputs the corresponding GF modules.

For example, to generate a GF abstract function and its Spanish and English linearizations for the concept of "able" (`able.a.01`), the script will:

1. **Query:** Select all lemmas for `synset_id = 'able.a.01'`.

1. **Generate Abstract:** Create a function like `Fun Able : A` (where `A` is the RGL category for adjectives).

1. **Generate Concrete (Eng):** Create a line in the English lexicon module: `lin Able = mkA "able"`.

1. **Generate Concrete (Spa):** Create a line in the Spanish lexicon module: `lin Able = mkA "capaz"`.

This process will automate the creation of thousands of lexicon entries, moving the project closer to a scalable translation system.

