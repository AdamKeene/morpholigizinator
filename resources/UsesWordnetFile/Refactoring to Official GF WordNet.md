# Refactoring to Official GF WordNet

This report documents the successful refactoring of the Grammatical Framework (GF) translation system to utilize the official **GF WordNet** source files, replacing the previous reliance on the NLTK WordNet and Open Multilingual WordNet (OMW) data. This change provides a significantly richer and more accurate lexicon, as the GF WordNet is explicitly designed for seamless integration with the GF Resource Grammar Library (RGL).

## 1. Rationale for Refactoring

The initial approach using NLTK's WordNet and OMW was a proof-of-concept. However, the official GF WordNet offers several key advantages essential for a robust GF-based translation system:

*   **Richer Linguistic Information**: The GF WordNet files contain not just the lemma, but the full GF linearization, including constructors (e.g., `mkN`, `mkV2`) and sometimes complex structures (e.g., `variants`, `compN`). This eliminates the need for manual mapping of simple lemmas to RGL constructors, which was a major limitation of the previous approach.
*   **Correct Categorization**: The GF WordNet functions are already categorized using the precise RGL categories (e.g., `V2` for transitive verbs, `N` for common nouns), which is crucial for building grammatically correct abstract syntax trees.
*   **Scale and Scope**: The official GF WordNet provides over 111,000 functions with both English and Spanish linearizations, a much larger and more consistent set than could be reliably extracted from the NLTK/OMW combination.

## 2. Implementation Details

The refactoring involved two main steps: data extraction and GF file generation.

### 2.1. Data Extraction from GF Source Files

A new Python script, **`parse_gf_wordnet.py`**, was developed to process the raw GF source files (`WordNet.gf`, `WordNetEng.gf`, `WordNetSpa.gf`) from the cloned `gf-wordnet` repository.

The script's primary function is to parse the `fun` and `lin` definitions and store them in a new SQLite database, **`gf_wordnet.db`**.

| Table | Column | Description |
| :--- | :--- | :--- |
| `functions` | `fun_name` | The GF function name (e.g., `abandon_1_V2`). |
| | `category` | The RGL category (e.g., `V2`, `N`). |
| | `eng_lin` | The full English linearization (e.g., `mkV2 (mkV "abandon")`). |
| | `spa_lin` | The full Spanish linearization (e.g., `mkV2 (mkV "abandonar")`). |

This process successfully extracted **111,619** functions with both English and Spanish linearizations, providing a massive, pre-validated lexicon.

### 2.2. Automated GF File Generation (v2)

The **`generate_gf_lexicon_v2.py`** script was updated to query the new `gf_wordnet.db`. Instead of trying to guess the RGL constructor, it now directly uses the `eng_lin` and `spa_lin` strings from the database.

The generated lexicon files (`WordNetLexiconV2.gf`, `WordNetLexiconV2Eng.gf`, `WordNetLexiconV2Spa.gf`) now contain the full, complex linearizations, ensuring linguistic accuracy.

## 3. System Verification

The final system, compiled into `WordNetTranslatorV2.pgf`, was verified to perform full sentence translation using the new, richer lexicon.

| Abstract Tree | Spanish Linearization | English Linearization |
| :--- | :--- | :--- |
| `Pred (UseN a_bomb_N) (UseV abate_2_V)` | `la bomba atómica cede` | `A-bomb abates` |
| `Pred (UseN a_bomb_N) (Compl abandon_1_V2 (UseN abaca_2_N))` | `la bomba atómica abandona abacá` | `A-bomb abandons abaca` |

The successful compilation and testing confirm that the system is now using the official GF WordNet, providing a much more robust and scalable foundation for the project.

## 4. Next Steps

The next phase of development should focus on expanding the abstract syntax (`WordNetTranslatorV2.gf`) to include more complex grammatical structures, such as:

1.  **Adjectives and Adverbs**: Integrating the `A` and `Adv` categories from the lexicon into the sentence structure.
2.  **Determiners**: Adding functions to correctly handle articles and quantifiers (e.g., `Det`, `Quant`).
3.  **Tense and Aspect**: Utilizing the RGL's functions for verb conjugation and tense marking.

This will move the system from simple subject-verb-object structures to more natural and expressive language.
