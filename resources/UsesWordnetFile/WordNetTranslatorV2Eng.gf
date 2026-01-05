concrete WordNetTranslatorV2Eng of WordNetTranslatorV2 = WordNetLexiconV2Eng ** open SyntaxEng, ParadigmsEng in {
  lincat
    S = SyntaxEng.S ;
    NP = SyntaxEng.NP ;
    VP = SyntaxEng.VP ;
  lin
    Pred np vp = mkS (mkCl np vp) ;
    Compl v2 np = mkVP v2 np ;
    UseN n = mkNP n ;
    UseV v = mkVP v ;
}
