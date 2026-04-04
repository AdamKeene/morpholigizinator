from django.contrib import admin

from .models import (
    SourceDocument, LexicalEntry, LexicalAlternate,
    GeneratedSentence, LessonSession, LessonWord,
    UserLanguageProfile, ExerciseAttempt,
)


@admin.register(SourceDocument)
class SourceDocumentAdmin(admin.ModelAdmin):
    list_display  = ("title", "imdb_id", "source_lang", "created_at")
    search_fields = ("title", "imdb_id")
    list_filter   = ("source_lang",)


class LexicalAlternateInline(admin.TabularInline):
    model  = LexicalAlternate
    extra  = 0
    fields = ("gf_function", "translations")
    readonly_fields = ("translations",)


class GeneratedSentenceInline(admin.TabularInline):
    model  = GeneratedSentence
    extra  = 0
    fields = ("label", "difficulty", "tree")
    readonly_fields = ("label", "difficulty", "tree")


@admin.register(LexicalEntry)
class LexicalEntryAdmin(admin.ModelAdmin):
    list_display  = ("word", "gf_function", "gf_cat", "in_wordnet", "updated_at")
    search_fields = ("word", "gf_function")
    list_filter   = ("in_wordnet", "gf_cat")
    inlines       = [LexicalAlternateInline, GeneratedSentenceInline]


@admin.register(LessonSession)
class LessonSessionAdmin(admin.ModelAdmin):
    list_display  = ("user", "source_doc", "source_lang", "target_lang", "created_at")
    list_filter   = ("source_lang", "target_lang")
    search_fields = ("user__username", "source_doc__title")


@admin.register(UserLanguageProfile)
class UserLanguageProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "source_lang", "target_lang", "updated_at")
    list_filter  = ("source_lang", "target_lang")


@admin.register(ExerciseAttempt)
class ExerciseAttemptAdmin(admin.ModelAdmin):
    list_display  = ("user", "exercise_type", "difficulty", "is_correct",
                     "target_lang", "created_at")
    list_filter   = ("exercise_type", "difficulty", "is_correct", "target_lang")
    search_fields = ("user__username", "gf_function")
    date_hierarchy = "created_at"
