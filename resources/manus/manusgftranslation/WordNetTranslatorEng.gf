concrete WordNetTranslatorEng of WordNetTranslator = WordNetLexiconEng ** open SyntaxEng, ParadigmsEng in {
  lincat
    S = SyntaxEng.S ;
    NP = SyntaxEng.NP ;
    VP = SyntaxEng.VP ;
    V2 = SyntaxEng.V2 ;
  lin
    Pred np vp = mkS (mkCl np vp) ;
    Compl v2 np = mkVP v2 np ;
    UseN n = mkNP n ;
    UseV v = mkVP v ;
    UseV2 v2 = v2 ;
}
