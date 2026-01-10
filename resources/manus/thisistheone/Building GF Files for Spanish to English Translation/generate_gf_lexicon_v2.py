import sqlite3
import os

def generate_gf_files(db_path, limit=1000):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    query = '''
    SELECT fun_name, category, eng_lin, spa_lin
    FROM functions
    WHERE eng_lin IS NOT NULL 
      AND spa_lin IS NOT NULL 
      AND eng_lin != 'variants {}'
      AND spa_lin != 'variants {}'
    LIMIT ?
    '''
    
    cursor.execute(query, (limit,))
    results = cursor.fetchall()
    
    abstract_entries = []
    english_entries = []
    spanish_entries = []
    
    categories = set()
    
    for fun_name, category, eng_lin, spa_lin in results:
        categories.add(category)
        abstract_entries.append(f"    {fun_name} : {category} ;")
        english_entries.append(f"    {fun_name} = {eng_lin} ;")
        spanish_entries.append(f"    {fun_name} = {spa_lin} ;")
        
    with open('WordNetLexiconV2.gf', 'w') as f:
        f.write("abstract WordNetLexiconV2 = {\n")
        f.write("  cat\n")
        f.write(f"    {' ; '.join(sorted(list(categories)))} ;\n")
        f.write("  fun\n")
        f.write("\n".join(abstract_entries))
        f.write("\n}\n")
        
    with open('WordNetLexiconV2Eng.gf', 'w') as f:
        f.write("concrete WordNetLexiconV2Eng of WordNetLexiconV2 = open MorphoEng, ResEng, ParadigmsEng, IrregEng, ExtraEng, (G = GrammarEng), (C = ConstructX), Prelude in {\n")
        f.write("  lincat\n")
        f.write("    N = G.N ; V = G.V ; A = G.A ; Adv = G.Adv ; V2 = G.V2 ; V3 = G.V3 ; VA = G.VA ; VS = G.VS ; PN = G.PN ; LN = G.LN ; AdA = G.AdA ; AdN = G.AdN ; N2 = G.N2 ; Prep = G.Prep ; A2 = G.A2 ;\n")
        f.write("  lin\n")
        f.write("\n".join(english_entries))
        f.write("\n}\n")
        
    with open('WordNetLexiconV2Spa.gf', 'w') as f:
        f.write("concrete WordNetLexiconV2Spa of WordNetLexiconV2 = open ConstructionSpa, GrammarSpa, ParadigmsSpa, ParamX, (S = StructuralSpa), (E = ExtendSpa), (L = LexiconSpa), (I = IrregSpa), (M = MorphoSpa), (R = ResSpa), Prelude in {\n")
        f.write("  lincat\n")
        f.write("    N = GrammarSpa.N ; V = GrammarSpa.V ; A = GrammarSpa.A ; Adv = GrammarSpa.Adv ; V2 = GrammarSpa.V2 ; V3 = GrammarSpa.V3 ; VA = GrammarSpa.VA ; VS = GrammarSpa.VS ; PN = GrammarSpa.PN ; LN = GrammarSpa.LN ; AdA = GrammarSpa.AdA ; AdN = GrammarSpa.AdN ; N2 = GrammarSpa.N2 ; Prep = GrammarSpa.Prep ; A2 = GrammarSpa.A2 ;\n")
        f.write("  lin\n")
        f.write("\n".join(spanish_entries))
        f.write("\n}\n")
        
    print(f"Generated GF files with {len(results)} entries.")
    conn.close()

if __name__ == "__main__":
    generate_gf_files('gf_wordnet.db', limit=1000)
