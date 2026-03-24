from translator import translate_document

translator = translate_document("resources/madagascar_srt/madagascar.srt", "es", "en")

inputs = ["Quiero ver ese arbol",
          "Se ve tan triste",
          "el pingüino corre",
          "mi pingüino corre",
          "mi troca"]
for i in inputs:
    result = translator(i)
    print(result, result.method)