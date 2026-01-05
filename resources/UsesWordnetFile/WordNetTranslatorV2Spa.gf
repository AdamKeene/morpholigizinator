concrete WordNetTranslatorV2Spa of WordNetTranslatorV2 = WordNetLexiconV2Spa ** open SyntaxSpa, ParadigmsSpa in {
  lincat
    S = SyntaxSpa.S ;
    NP = SyntaxSpa.NP ;
    VP = SyntaxSpa.VP ;
  lin
    Pred np vp = mkS (mkCl np vp) ;
    Compl v2 np = mkVP v2 np ;
    UseN n = mkNP n ;
    UseV v = mkVP v ;
}
