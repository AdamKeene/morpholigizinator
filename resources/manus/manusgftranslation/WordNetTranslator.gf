abstract WordNetTranslator = WordNetLexicon ** {
  flags startcat = S ;
  cat
    S ; NP ; VP ; V2 ;
  fun
    Pred : NP -> VP -> S ;
    Compl : V2 -> NP -> VP ;
    UseN : N -> NP ;
    UseV : V -> VP ;
    UseV2 : V2 -> V2 ;
}
