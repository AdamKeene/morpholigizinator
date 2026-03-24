import unittest
import os
import sys
import numpy as np
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from multilingual_pipeline import (
    extract_keywords,
    semantic_expansion,
    translate_lexicon,
    generate_gf_file,
    LANG_CONFIG
)

# --- Mock Classes to simulate external libraries ---

class MockSpaCyToken:
    def __init__(self, lemma, is_stop=False, is_punct=False, is_space=False, is_digit=False):
        self.lemma_ = lemma
        self.is_stop = is_stop
        self.is_punct = is_punct
        self.is_space = is_space
        self.is_digit = is_digit

class MockSpaCyDoc:
    def __init__(self, tokens):
        self.tokens = tokens
    def __iter__(self):
        return iter(self.tokens)

def mock_spacy_load(model_name):
    return lambda text: MockSpaCyDoc([MockSpaCyToken('electric'), MockSpaCyToken('vehicle')])

class MockKeyedVectors:
    def most_similar(self, keyword, topn=10):
        return [(f"similar_to_{keyword}", 0.9)]

# --- The Test Suite ---

class TestMultilingualPipeline(unittest.TestCase):

    def setUp(self):
        for lang_code in LANG_CONFIG:
            vec_path = LANG_CONFIG[lang_code]["fasttext_vec"]
            os.makedirs(os.path.dirname(vec_path), exist_ok=True)
            with open(vec_path, "w") as f:
                f.write("1 1\nword 1\n")
        with open("sample.txt", "w") as f:
            f.write("This is a test document.")

    def tearDown(self):
        for lang_code in LANG_CONFIG:
            if os.path.exists(LANG_CONFIG[lang_code]["fasttext_vec"]):
                os.remove(LANG_CONFIG[lang_code]["fasttext_vec"])
        if os.path.exists("sample.txt"): os.remove("sample.txt")
        if os.path.exists("ExpandedLexiconTest.gf"): os.remove("ExpandedLexiconTest.gf")

    @patch('spacy.load', side_effect=mock_spacy_load)
    @patch('sklearn.feature_extraction.text.TfidfVectorizer')
    @patch('sklearn.decomposition.LatentDirichletAllocation')
    def test_extract_keywords(self, mock_lda, mock_tfidf, mock_spacy_load):
        mock_tfidf_instance = mock_tfidf.return_value
        mock_tfidf_instance.get_feature_names_out.return_value = ['electric', 'vehicle']
        mock_lda_instance = mock_lda.return_value
        mock_lda_instance.components_ = np.array([[0.9, 0.1]])
        
        keywords = extract_keywords('text', 'en', n_topics=1, n_words=1)
        self.assertEqual(keywords, ['electric'])

    @patch('gensim.models.KeyedVectors.load_word2vec_format', return_value=MockKeyedVectors())
    def test_semantic_expansion(self, mock_load_word2vec_format):
        initial_keywords = ['battery']
        # The function being tested adds the original keyword to the list of similar words
        expanded_lexicon = semantic_expansion(initial_keywords, 'en', top_n=1)
        self.assertEqual(sorted(expanded_lexicon), sorted(['battery', 'similar_to_battery']))

    @patch('multilingual_pipeline.MarianMT_LANG_MAP', {"en-es": "Helsinki-NLP/opus-mt-en-es"})
    @patch('transformers.AutoModelForSeq2SeqLM.from_pretrained')
    @patch('transformers.AutoTokenizer.from_pretrained')
    def test_translation_marian(self, mock_tokenizer, mock_model):
        mock_tokenizer_instance = mock_tokenizer.return_value
        mock_tokenizer_instance.decode.side_effect = ['batería', 'coche']
        mock_model_instance = mock_model.return_value
        mock_model_instance.generate.return_value = [[1,2,3], [4,5,6]]

        translated_words = translate_lexicon(['battery', 'car'], 'en', 'es')
        self.assertEqual(translated_words, ['batería', 'coche'])

    def test_generate_gf_file(self):
        output_path = generate_gf_file(['battery'], ['batería'], 'Test')
        self.assertTrue(os.path.exists(output_path))
        with open(output_path, 'r') as f:
            content = f.read()
            self.assertIn('concrete ExpandedLexiconTest of Words', content)
            # Sanitize fun_name for the check
            self.assertIn('Battery_0 : CN = {s = "batería"};', content.replace(".", ""))

if __name__ == '__main__':
    unittest.main(argv=['first-arg-is-ignored'], exit=False)
