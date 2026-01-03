abstract RGLTranslator = {
  flags startcat = S ;
  cat
    S ; NP ; VP ; V2 ;
  fun
    Pred : NP -> VP -> S ;
    Compl : V2 -> NP -> VP ;
    John, Mary : NP ;
    Love, Eat : V2 ;
    Apple, Pizza : NP ;
}
