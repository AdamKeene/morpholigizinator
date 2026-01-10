concrete TranslatorEng of Translator = {
  lincat
    Phrase = {s : Str} ;
    Subject = {s : Str} ;
    Verb = {s : Str} ;
    Object = {s : Str} ;
  lin
    PredVP subj verb obj = {s = subj.s ++ verb.s ++ obj.s} ;
    John = {s = "John"} ;
    Mary = {s = "Mary"} ;
    Love = {s = "loves"} ;
    Eat = {s = "eats"} ;
    Apple = {s = "an apple"} ;
    Pizza = {s = "a pizza"} ;
}
