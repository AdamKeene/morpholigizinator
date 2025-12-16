# GF Lexicon Generation System: Implementation Report

This report details the implementation of a system designed to automatically generate a broad, subject-matter-specific Grammatical Framework (GF) lexicon by combining Topic Modeling and Neural Word Embeddings.

## System Overview

The system operates in a three-stage pipeline:

1.  **Subject Matter Extraction (Topic Modeling):** The source document is analyzed using Latent Dirichlet Allocation (LDA) to identify core topics and extract a list of high-relevance keywords.
2.  **Lexicon Expansion (Word Embeddings):** The extracted keywords are used as seeds in a pre-trained word embedding model (GloVe) to find a large set of semantically related words.
3.  **GF Lexicon Formatting:** The expanded vocabulary is formatted into a valid GF concrete syntax file, ready for import into a GF grammar.

## Implementation Details

### 1. Subject Matter Extraction (Phase 1)

The goal of this phase was to distill the document's content into a manageable list of subject keywords.

*   **Tool:** Python with `scikit-learn` (for LDA) and `nltk` (for preprocessing).
*   **Process:**
    1.  A sample document on **Electric Vehicles and Battery Technology** was created.
    2.  The text was preprocessed (tokenization, stop-word removal, lemmatization).
    3.  LDA was applied to the document-term matrix, configured to find 3 topics.
    4.  The top 10 words from each topic were combined to form the subject keyword list.
*   **Result:** The process yielded **28 unique subject keywords** (e.g., `cathode`, `cobalt`, `supply`, `energy`, `vehicle`), which were saved to `/home/ubuntu/subject_keywords.txt`.

### 2. Lexicon Expansion (Phase 2)

This phase leveraged the semantic clustering property of neural networks to expand the subject keywords into a comprehensive vocabulary.

*   **Tool:** Python with `gensim` (for word embedding operations).
*   **Model:** The pre-trained `glove-wiki-gigaword-50` model was used.
*   **Process:**
    1.  The script iterated through the 28 subject keywords.
    2.  For each keyword, it queried the GloVe model for the **top 20 most similar words** based on cosine similarity.
    3.  The results were collected into a single set to ensure uniqueness.
*   **Result:** The expansion process resulted in a total of **498 unique, semantically related words**, saved to `/home/ubuntu/expanded_lexicon.txt`.

### 3. GF Lexicon Formatting (Phase 3)

The final step converted the raw word list into a GF-compatible file.

*   **Tool:** Python script.
*   **Assumptions (Customizable):**
    *   **Target Language:** English (placeholder).
    *   **GF Category:** `CN` (Common Noun).
    *   **GF Module Name:** `ExpandedLexiconEng`.
*   **GF Syntax Generated:**
    The script generated a concrete syntax module with a simplified linearization for common nouns:
    ```gf
    concrete ExpandedLexiconEng of Words = {
      lincat CN = {s : Str};
      lin
        word_CN : CN = {s = "word"}
        ...
    }
    ```
*   **Result:** The final GF lexicon file, `/home/ubuntu/ExpandedLexicon.gf`, contains 498 entries, ready to be imported into a GF abstract syntax module.

## Usage Instructions

To replicate and use this system:

1.  **Setup:** Ensure you have Python 3.11, `nltk`, `scikit-learn`, and `gensim` installed (preferably in a virtual environment).
2.  **Source Document:** Place your source text in `/home/ubuntu/sample_document.txt`.
3.  **Run Topic Modeling:** Execute `/home/ubuntu/topic_modeling.py`. This will generate `/home/ubuntu/subject_keywords.txt`.
4.  **Run Lexicon Expansion:** Execute `/home/ubuntu/lexicon_expansion.py`. This will download the GloVe model (if not already present) and generate `/home/ubuntu/expanded_lexicon.txt`.
5.  **Generate GF File:** Execute `/home/ubuntu/generate_gf_lexicon.py`. This will create the final GF file at `/home/ubuntu/ExpandedLexicon.gf`.

### Customization Notes

*   **Target Language:** To generate a lexicon for a different target language (e.g., Spanish), you would need to:
    *   Use a **bilingual word embedding model** or a **translation step** between Phase 2 and Phase 3.
    *   Update the `generate_gf_lexicon.py` script to use the correct GF module name and the appropriate linearization function for the target language (e.g., a function that handles Spanish noun gender and number inflection).
*   **GF Category:** To change the GF category (e.g., to `V` for verbs), update the `GF_CATEGORY` variable in `generate_gf_lexicon.py` and ensure the linearization function is correct.

## Attached Files

| File Name | Description |
| :--- | :--- |
| `topic_modeling.py` | Python script for extracting subject keywords using LDA. |
| `lexicon_expansion.py` | Python script for expanding keywords using GloVe word embeddings. |
| `generate_gf_lexicon.py` | Python script for formatting the expanded list into a GF concrete syntax file. |
| `sample_document.txt` | The sample source text used for the demonstration. |
| `ExpandedLexicon.gf` | The final generated GF lexicon file (498 entries). |
| `subject_keywords.txt` | The 28 keywords extracted by the topic model. |
| `expanded_lexicon.txt` | The 498 raw words generated by the word embedding model. |
| `GF_Lexicon_Generation_Report.md` | This report. |
