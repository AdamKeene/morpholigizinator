import subprocess
import sqlite3
import sys

class GFTranslator:
    def __init__(self, pgf_path, db_path):
        self.pgf_path = pgf_path
        self.db_path = db_path
        
    def _run_gf_command(self, command):
        full_command = f'echo "{command}" | gf --run {self.pgf_path}'
        process = subprocess.Popen(full_command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        stdout, stderr = process.communicate()
        if process.returncode != 0:
            return f"Error: {stderr}"
        return stdout.strip()

    def translate_spa_to_eng(self, text):
        print(f"Translating (ES -> EN): {text}")
        # Command: p -lang=WordNetTranslatorV3Spa "text" | l -lang=WordNetTranslatorV3Eng
        cmd = f'p -lang=WordNetTranslatorV3Spa \\"{text}\\" | l -lang=WordNetTranslatorV3Eng'
        result = self._run_gf_command(cmd)
        return result.split('\n')

    def translate_eng_to_spa(self, text):
        print(f"Translating (EN -> ES): {text}")
        # Command: p -lang=WordNetTranslatorV3Eng "text" | l -lang=WordNetTranslatorV3Spa
        cmd = f'p -lang=WordNetTranslatorV3Eng \\"{text}\\" | l -lang=WordNetTranslatorV3Spa'
        result = self._run_gf_command(cmd)
        return result.split('\n')

if __name__ == "__main__":
    PGF_PATH = "WordNetTranslatorV3.pgf"
    DB_PATH = "gf_wordnet.db"
    
    translator = GFTranslator(PGF_PATH, DB_PATH)
    
    # Example translations
    test_sentences_spa = [
        "la bomba atómica cede",
        "cada bomba atómica abandona abacá"
    ]
    
    for sent in test_sentences_spa:
        results = translator.translate_spa_to_eng(sent)
        print(f"Results: {results}\n")
        
    test_sentences_eng = [
        "the A-bomb abates",
        "every A-bomb abandons abaca"
    ]
    
    for sent in test_sentences_eng:
        results = translator.translate_eng_to_spa(sent)
        print(f"Results: {results}\n")
