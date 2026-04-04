from django.contrib.auth.models import User
from rest_framework import serializers

from .models import (
    ExerciseAttempt,
    GeneratedSentence,
    LessonSession,
    LessonWord,
    LexicalAlternate,
    LexicalEntry,
    SourceDocument,
    UserLanguageProfile,
)


class SourceDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model  = SourceDocument
        fields = ["id", "title", "imdb_id", "source_lang", "created_at"]
        read_only_fields = ["id", "created_at"]


class LexicalAlternateSerializer(serializers.ModelSerializer):
    class Meta:
        model  = LexicalAlternate
        fields = ["gf_function", "translations"]


class GeneratedSentenceSerializer(serializers.ModelSerializer):
    class Meta:
        model  = GeneratedSentence
        fields = ["id", "label", "tree", "pattern", "linearizations", "difficulty"]


class LexicalEntrySerializer(serializers.ModelSerializer):
    alternates = LexicalAlternateSerializer(many=True, read_only=True)
    sentences  = GeneratedSentenceSerializer(many=True, read_only=True)

    class Meta:
        model  = LexicalEntry
        fields = [
            "id", "word", "gf_function", "gf_cat", "in_wordnet",
            "translations", "alternates", "sentences",
        ]


class LessonWordSerializer(serializers.ModelSerializer):
    entry = LexicalEntrySerializer(read_only=True)

    class Meta:
        model  = LessonWord
        fields = ["id", "entry", "source_count", "alternate_counts"]


class LessonSessionSerializer(serializers.ModelSerializer):
    word_count = serializers.SerializerMethodField()

    class Meta:
        model  = LessonSession
        fields = [
            "id", "source_doc", "source_lang", "target_lang",
            "status", "task_id", "created_at", "word_count",
        ]
        read_only_fields = ["id", "status", "task_id", "created_at", "word_count"]

    def get_word_count(self, obj):
        return obj.lesson_words.count()


class ExerciseAttemptSerializer(serializers.ModelSerializer):
    class Meta:
        model  = ExerciseAttempt
        fields = [
            "id", "exercise_type", "difficulty", "pattern",
            "gf_function", "gf_cat", "prompt", "prompt_lang", "target_lang",
            "correct_answer", "user_answer", "is_correct",
            "response_time_ms", "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class SkillProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model  = UserLanguageProfile
        fields = ["source_lang", "target_lang", "skill_data", "updated_at"]
        read_only_fields = ["updated_at"]


# ---------------------------------------------------------------------------
# Auth serializers
# ---------------------------------------------------------------------------

class RegisterSerializer(serializers.ModelSerializer):
    password  = serializers.CharField(write_only=True, min_length=8)
    password2 = serializers.CharField(write_only=True, label="Confirm password")

    class Meta:
        model  = User
        fields = ["username", "email", "password", "password2"]

    def validate(self, data):
        if data["password"] != data["password2"]:
            raise serializers.ValidationError({"password2": "Passwords do not match."})
        return data

    def create(self, validated_data):
        validated_data.pop("password2")
        return User.objects.create_user(**validated_data)
