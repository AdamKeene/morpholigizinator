concrete RGLTranslatorSpa of RGLTranslator = open SyntaxSpa, ParadigmsSpa in {
  lincat
    S = SyntaxSpa.S ;
    NP = SyntaxSpa.NP ;
    VP = SyntaxSpa.VP ;
    V2 = SyntaxSpa.V2 ;
  lin
    Pred np vp = mkS (mkCl np vp) ;
    Compl v2 np = mkVP v2 np ;
    John = mkNP (mkPN "Juan") ;
    Mary = mkNP (mkPN "María") ;
    Love = mkV2 (mkV "amar") ;
    Eat = mkV2 (mkV "comer") ;
    Apple = mkNP (mkN "manzana") ;
    Pizza = mkNP (mkN "pizza") ;
}
