concrete WordNetTranslatorSpa of WordNetTranslator = WordNetLexiconSpa ** open SyntaxSpa, ParadigmsSpa in {
  lincat
    S = SyntaxSpa.S ;
    NP = SyntaxSpa.NP ;
    VP = SyntaxSpa.VP ;
    V2 = SyntaxSpa.V2 ;
  lin
    Pred np vp = mkS (mkCl np vp) ;
    Compl v2 np = mkVP v2 np ;
    UseN n = mkNP n ;
    UseV v = mkVP v ;
    UseV2 v2 = v2 ;
}
