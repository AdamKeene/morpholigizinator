concrete TranslatorSpa of Translator = {
  lincat
    Phrase = {s : Str} ;
    Subject = {s : Str} ;
    Verb = {s : Str} ;
    Object = {s : Str} ;
  lin
    PredVP subj verb obj = {s = subj.s ++ verb.s ++ obj.s} ;
    John = {s = "Juan"} ;
    Mary = {s = "María"} ;
    Love = {s = "ama a"} ;
    Eat = {s = "come"} ;
    Apple = {s = "una manzana"} ;
    Pizza = {s = "una pizza"} ;
}
