concrete WordNetTranslatorV3Spa of WordNetTranslatorV3 = WordNetLexiconV2Spa ** open SyntaxSpa, ParadigmsSpa in {
  lincat
    S = SyntaxSpa.S ;
    NP = SyntaxSpa.NP ;
    VP = SyntaxSpa.VP ;
    AP = SyntaxSpa.AP ;
    Det = SyntaxSpa.Det ;
    CN = SyntaxSpa.CN ;
  lin
    Pred np vp = mkS (mkCl np vp) ;
    
    UseV v = mkVP v ;
    Compl v2 np = mkVP v2 np ;
    AdvVP vp adv = mkVP vp adv ;
    
    DetCN det cn = mkNP det cn ;
    UseN n = mkNP n ;
    
    ModCN ap cn = mkCN ap cn ;
    UseN_CN n = mkCN n ;
    
    PositA a = mkAP a ;
    
    the_Det = SyntaxSpa.the_Det ;
    a_Det = SyntaxSpa.a_Det ;
    every_Det = SyntaxSpa.every_Det ;
}
