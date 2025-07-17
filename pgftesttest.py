# https://www.grammaticalframework.org/lib/doc/absfuns.html

import pgf
# from chart import cats

parse_file = pgf.readPGF("EnEsParse.pgf")
parse_en = parse_file.languages["ParseEng"]
parse_es = parse_file.languages["ParseSpa"]
parsers = {
    "en": parse_en, 
    "es": parse_es}

wordnet_file = pgf.readPGF("WordNet.pgf")

wordnet_en = wordnet_file.languages["WordNetEng"]
wordnet_es = wordnet_file.languages["WordNetSpa"]
wordnets = {
    "en": wordnet_en,
    "es": wordnet_es
}

def translate(text, source_lang, target_lang):
    parser = parsers[source_lang]
    wordnet = wordnets[target_lang]

    parsed = parser.parse(text)
    for tree, expr in parsed:
        linearized = wordnet.linearize(expr)
        print(f"Original: {text}\nTranslated: {linearized}\n")
        return linearized
    
translate("cat", 'en', 'es')