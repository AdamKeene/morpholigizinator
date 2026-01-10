abstract WordNetTranslatorV3 = WordNetLexiconV2 ** {
  flags startcat = S ;
  cat
    S ; NP ; VP ; AP ; Det ; CN ;
  fun
    -- Sentence structures
    Pred : NP -> VP -> S ;
    
    -- Verb Phrase structures
    UseV : V -> VP ;
    Compl : V2 -> NP -> VP ;
    AdvVP : VP -> Adv -> VP ;
    
    -- Noun Phrase structures
    DetCN : Det -> CN -> NP ;
    UseN : N -> NP ; -- Simplified NP from N
    
    -- Common Noun structures
    ModCN : AP -> CN -> CN ;
    UseN_CN : N -> CN ;
    
    -- Adjective Phrase structures
    PositA : A -> AP ;
    
    -- Determiners
    the_Det : Det ;
    a_Det : Det ;
    every_Det : Det ;
}
