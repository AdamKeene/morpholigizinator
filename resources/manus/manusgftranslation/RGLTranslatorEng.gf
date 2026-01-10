concrete RGLTranslatorEng of RGLTranslator = open SyntaxEng, ParadigmsEng in {
  lincat
    S = SyntaxEng.S ;
    NP = SyntaxEng.NP ;
    VP = SyntaxEng.VP ;
    V2 = SyntaxEng.V2 ;
  lin
    Pred np vp = mkS (mkCl np vp) ;
    Compl v2 np = mkVP v2 np ;
    John = mkNP (mkPN "John") ;
    Mary = mkNP (mkPN "Mary") ;
    Love = mkV2 (mkV "love") ;
    Eat = mkV2 (mkV "eat") ;
    Apple = mkNP (mkN "apple") ;
    Pizza = mkNP (mkN "pizza") ;
}
