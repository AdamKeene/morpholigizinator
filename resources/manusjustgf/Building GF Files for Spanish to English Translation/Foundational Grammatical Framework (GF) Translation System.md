# Foundational Grammatical Framework (GF) Translation System

This report details the initial implementation of a Spanish-to-English translation system using the Grammatical Framework (GF). This foundational work is designed to be a verifiable starting point for the user's ultimate goal of building a robust system that integrates the Resource Grammar Library (RGL) and WordNet for lexicon generation.

## 1. Implementation Overview

Two sets of grammar files were created to demonstrate the core GF concepts and establish a link to the RGL, which is essential for the next phase of development.

### 1.1. Basic Grammar (Verification)

A simple, self-contained grammar was created to quickly verify the GF installation and the concept of abstract and concrete syntax.

| File Name | Type | Purpose |
| :--- | :--- | :--- |
| `Translator.gf` | Abstract Syntax | Defines the common structure for simple sentences (e.g., `PredVP : Subject -> Verb -> Object -> Phrase`). |
| `TranslatorEng.gf` | Concrete Syntax | Provides English linearizations for the abstract functions (e.g., `Love = {s = "loves"}`). |
| `TranslatorSpa.gf` | Concrete Syntax | Provides Spanish linearizations for the abstract functions (e.g., `Love = {s = "ama a"}`). |

This basic grammar successfully translated a simple sentence:

> **Input (Spanish):** `Juan come una pizza`
> **Output (English):** `John eats a pizza`

### 1.2. RGL-Based Grammar (Foundation)

The core of the system is built on the RGL, which provides rich morphological and syntactic information for both languages. This significantly reduces the manual effort required for complex linguistic features.

| File Name | Type | Purpose |
| :--- | :--- | :--- |
| `RGLTranslator.gf` | Abstract Syntax | Defines a more standard GF abstract syntax using RGL categories (`S`, `NP`, `VP`, `V2`). |
| `RGLTranslatorEng.gf` | Concrete Syntax | Imports RGL modules (`SyntaxEng`, `ParadigmsEng`) to provide linguistically informed English linearizations. |
| `RGLTranslatorSpa.gf` | Concrete Syntax | Imports RGL modules (`SyntaxSpa`, `ParadigmsSpa`) to provide linguistically informed Spanish linearizations. |

The RGL-based grammar was successfully compiled by setting the GF path to include the necessary RGL source directories:

```bash
gf -make -path=.:/home/ubuntu/gf-rgl/src/api:/home/ubuntu/gf-rgl/src/english:/home/ubuntu/gf-rgl/src/spanish:/home/ubuntu/gf-rgl/src/abstract:/home/ubuntu/gf-rgl/src/common:/home/ubuntu/gf-rgl/src/prelude:/home/ubuntu/gf-rgl/src/romance RGLTranslatorSpa.gf RGLTranslatorEng.gf
```

This setup allows the grammar to leverage the full power of the RGL, including correct verb conjugation and noun-phrase structure, as demonstrated by the successful translation:

| Abstract Tree | Spanish Linearization | English Linearization |
| :--- | :--- | :--- |
| `Pred John (Compl Love Mary)` | `Juan ama María` | `John loves Mary` |

## 2. Next Steps: Integrating WordNet for Lexicon Generation

The next critical step, as outlined in the initial request, is to integrate WordNet to automate the creation of the GF lexicon. This approach will move beyond manually defining words in the concrete syntax files and allow for large-scale, data-driven lexicon expansion.

The proposed plan for this integration is as follows:

| Phase | Goal | Required Tools/Skills |
| :--- | :--- | :--- |
| **2.1. WordNet Data Extraction** | Load the WordNet data (specifically the Spanish and English components) into a structured, easily accessible format, such as a Python dictionary or a simple text file, to serve as the source of truth for the lexicon. | Python, Data Parsing |
| **2.2. Lexicon Generation Script** | Develop a Python script that iterates over the WordNet data, extracts the relevant words and their corresponding parts-of-speech (POS) and senses (synsets), and generates GF lexicon modules (`.gf` files). | Python, Technical Writing (GF syntax) |
| **2.3. GF Lexicon Integration** | Modify the `RGLTranslatorEng.gf` and `RGLTranslatorSpa.gf` files to import the newly generated lexicon modules. This will replace the manually defined functions (`John`, `Love`, `Pizza`, etc.) with functions generated from WordNet. | GF Compiler, RGL Knowledge |
| **2.4. Embedding-Based Expansion** | Explore the use of word embeddings to identify new words or phrases that are semantically similar to existing lexicon entries, further automating the lexicon creation process. | Python, NLP Libraries (e.g., Gensim, spaCy) |

This structured approach ensures that the system is built on a solid GF and RGL foundation, with the WordNet integration providing the scalable lexicon required for a practical translation system.

## 3. Provided Files

The following files are provided as the successful output of this foundational phase:

*   `RGLTranslator.gf`
*   `RGLTranslatorEng.gf`
*   `RGLTranslatorSpa.gf`
*   `Translator.pgf` (The compiled RGL-based grammar)
*   `GF_Translation_System_Report.md` (This document)

The basic grammar files (`Translator.gf`, `TranslatorEng.gf`, `TranslatorSpa.gf`) are also available in the working directory.
