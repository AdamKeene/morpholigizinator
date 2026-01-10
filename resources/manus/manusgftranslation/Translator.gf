abstract Translator = {
  flags startcat = Phrase ;
  cat
    Phrase ; 
    Subject ; 
    Verb ; 
    Object ;
  fun
    PredVP : Subject -> Verb -> Object -> Phrase ;
    John : Subject ;
    Mary : Subject ;
    Love : Verb ;
    Eat : Verb ;
    Apple : Object ;
    Pizza : Object ;
}
