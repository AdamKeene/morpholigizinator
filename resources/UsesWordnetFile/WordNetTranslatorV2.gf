abstract WordNetTranslatorV2 = WordNetLexiconV2 ** {
  flags startcat = S ;
  cat
    S ; NP ; VP ;
  fun
    Pred : NP -> VP -> S ;
    Compl : V2 -> NP -> VP ;
    UseN : N -> NP ;
    UseV : V -> VP ;
}
