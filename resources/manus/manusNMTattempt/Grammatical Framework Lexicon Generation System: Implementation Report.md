# Grammatical Framework Lexicon Generation System: Implementation Report

**Author:** Manus AI
**Date:** December 13, 2025

## 1. Introduction

This report details the implementation of a system designed to automatically generate a broad, subject-matter-specific lexicon for Grammatical Framework (GF) in a target language. The goal is to enrich the vocabulary available to a GF grammar for a specific domain (e.g., electric vehicles, as used in the sample) by leveraging neural network technology for semantic expansion and translation.

The final implemented pipeline consists of three main stages: **Subject Matter Extraction**, **Semantic Expansion**, and **Translation & GF Formatting**.

## 2. System Architecture and Implementation

The system is implemented as a pipeline of three Python scripts, executed sequentially.

### 2.1. Stage 1: Subject Matter Extraction (Topic Modeling)

The initial stage identifies the core vocabulary of the source document.

| Component | Tool/Library | Function | Output |
| :--- | :--- | :--- | :--- |
| **Script** | `topic_modeling.py` | Latent Dirichlet Allocation (LDA) | `subject_keywords.txt` |
| **Process** | The script uses **scikit-learn's LDA** to analyze the source text (`sample_document.txt`). It extracts a set of high-probability keywords for the identified topics, representing the document's subject matter. |

### 2.2. Stage 2: Semantic Expansion (Word Embeddings)

This stage uses a pre-trained word embedding model to find words semantically related to the subject keywords, creating a large, domain-relevant vocabulary.

| Component | Tool/Library | Function | Output |
| :--- | :--- | :--- | :--- |
| **Script** | `lexicon_expansion.py` | Gensim, GloVe | `expanded_lexicon.txt` |
| **Process** | The script loads the **GloVe word embedding model** and queries it for the top $N$ most similar words for each subject keyword. This generates a large list of unique, related English words (e.g., 498 words from the sample). |

### 2.3. Stage 3: Translation and GF Formatting

This stage translates the expanded English lexicon into the target language (Spanish) using a lightweight NMT model and formats the result into a valid GF concrete syntax file.

| Component | Tool/Library | Function | Output |
| :--- | :--- | :--- | :--- |
| **Script** | `translate_lexicon_simple.py` | Hugging Face `transformers`, MarianMT | `translated_lexicon_es.txt` |
| **Process** | The script uses the **Helsinki-NLP/opus-mt-en-es MarianMT model** for fast, local, single-word translation. It translates the entire expanded lexicon from English to Spanish. **Note:** Due to implementation challenges and the user's request for speed, the initial plan for Part-of-Speech (POS) tagging was omitted. All words are currently assigned the default GF category **Common Noun (`CN`)**. |
| **Script** | `generate_gf_lexicon_es.py` | Python | `ExpandedLexiconSpa.gf` |
| **Process** | This script reads the translated data and formats it into a GF concrete syntax module named `ExpandedLexiconSpa`. Each entry is linearized as a simple, uninflected Common Noun. |

## 3. Usage Instructions

To run the complete pipeline:

1.  **Setup:** Ensure you have the virtual environment active and all dependencies installed (`scikit-learn`, `gensim`, `transformers`, `torch`).
2.  **Input:** Place your source text in `/home/ubuntu/sample_document.txt`.
3.  **Execution:** Run the scripts in the following order:

    ```bash
    # 1. Extract Subject Keywords
    python3.11 /home/ubuntu/topic_modeling.py

    # 2. Expand Lexicon
    python3.11 /home/ubuntu/lexicon_expansion.py

    # 3. Translate Lexicon (to Spanish)
    python3.11 /home/ubuntu/translate_lexicon_simple.py

    # 4. Generate GF File
    python3.11 /home/ubuntu/generate_gf_lexicon_es.py
    ```

The final output, `ExpandedLexiconSpa.gf`, will be ready for use in your GF grammar.

## 4. Future Work and Customization

### 4.1. Target Language Customization

To change the target language:

1.  **Update NMT Model:** In `translate_lexicon_simple.py`, change `MODEL_NAME` to a different MarianMT model (e.g., `Helsinki-NLP/opus-mt-en-fr` for French).
2.  **Update GF Module:** In `generate_gf_lexicon_es.py`, change `OUTPUT_PATH` and `MODULE_NAME` (e.g., to `ExpandedLexiconFre.gf`).

### 4.2. Re-introducing POS Tagging

The current lexicon uses the simplified `CN` category for all words. For a production-ready GF grammar, it is highly recommended to re-introduce the POS tagging step (Option B from our discussion). This would involve:

1.  **Fixing NLTK:** Resolving the NLTK resource loading issue (which was the primary roadblock in the previous attempts).
2.  **Updating GF Formatting:** Modifying `generate_gf_lexicon_es.py` to use language-specific inflection functions (e.g., `mkN`, `mkV`, `mkA`) instead of the generic `{s = "word"}` linearization, which is necessary for grammatically correct GF output.

## 5. Conclusion

The system successfully demonstrates the feasibility of using neural network components (word embeddings and NMT) to automate the creation of large, domain-specific GF lexicons. The resulting Spanish lexicon, `ExpandedLexiconSpa.gf`, provides a rich vocabulary for the domain of electric vehicles, ready to be integrated into a GF abstract syntax.

## References

No external sources were used in the final implementation. All models (GloVe, MarianMT) were loaded via their respective Python libraries (Gensim, Hugging Face `transformers`).
