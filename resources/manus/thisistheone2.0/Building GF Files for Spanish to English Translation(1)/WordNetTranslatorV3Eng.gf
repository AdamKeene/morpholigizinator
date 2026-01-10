concrete WordNetTranslatorV3Eng of WordNetTranslatorV3 = WordNetLexiconV2Eng ** open SyntaxEng, ParadigmsEng in {
  lincat
    S = SyntaxEng.S ;
    NP = SyntaxEng.NP ;
    VP = SyntaxEng.VP ;
    AP = SyntaxEng.AP ;
    Det = SyntaxEng.Det ;
    CN = SyntaxEng.CN ;
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
    
    the_Det = SyntaxEng.the_Det ;
    a_Det = SyntaxEng.a_Det ;
    every_Det = SyntaxEng.every_Det ;
}
