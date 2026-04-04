"""
ORM models for the morpholigizinator language-learning system.

Conceptual layers
-----------------
1. Source content  — SourceDocument, SourceSentence
2. Lexical cache   — LexicalEntry, LexicalAlternate, GeneratedSentence
3. Session layer   — LessonSession, LessonWord
4. Skill tracking  — UserLanguageProfile
5. Exercise log    — ExerciseAttempt
"""

from django.contrib.auth.models import User
from django.db import models


# ---------------------------------------------------------------------------
# 1. Source content
# ---------------------------------------------------------------------------

class SourceDocument(models.Model):
    """
    A source text (subtitle file, article, etc.) that lessons are built from.
    """
    title       = models.CharField(max_length=300)
    imdb_id     = models.CharField(max_length=20, blank=True, db_index=True)
    source_lang = models.CharField(max_length=10)          # ISO 639-1 code, e.g. "en"
    raw_text    = models.TextField(blank=True)              # extracted subtitle text
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("imdb_id", "source_lang")]

    def __str__(self):
        return f"{self.title} [{self.source_lang}]"


# ---------------------------------------------------------------------------
# 2. Lexical cache  (deterministic GF output, keyed by word + gf_function)
# ---------------------------------------------------------------------------

class LexicalEntry(models.Model):
    """
    One vocabulary item as produced by build_lesson(), cached in the database.

    A LexicalEntry is shared across all users and sessions: same GF function →
    same translations and sentences.  Session-specific data (source_count) lives
    in LessonWord.
    """
    word        = models.CharField(max_length=200, db_index=True)
    gf_function = models.CharField(max_length=200, blank=True, db_index=True)
    gf_cat      = models.CharField(max_length=20, blank=True)   # "N", "V", "V2", "A", "Adv"
    in_wordnet  = models.BooleanField(default=False)
    translations = models.JSONField(default=dict)               # {lang: word}
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("word", "gf_function")]

    def __str__(self):
        fn = self.gf_function or "(OOV)"
        return f"{self.word} / {fn}"


class LexicalAlternate(models.Model):
    """
    An alternate sense for a LexicalEntry (different GF function, distinct translation).

    Corresponds to the 'alternates' list in build_lesson() output.
    """
    entry       = models.ForeignKey(LexicalEntry, on_delete=models.CASCADE,
                                    related_name="alternates")
    gf_function = models.CharField(max_length=200)
    translations = models.JSONField(default=dict)   # {lang: word}

    class Meta:
        unique_together = [("entry", "gf_function")]

    def __str__(self):
        return f"alt:{self.gf_function} for {self.entry}"


class GeneratedSentence(models.Model):
    """
    One GF-generated sentence for a lexical entry.

    Stores the raw GF tree string and all linearizations so they do not need to
    be recomputed on each request.  The 'pattern' JSON mirrors GrammarPattern
    fields (utt_type, tense, aspect, polarity, person, verb_cat, progressive,
    attributive, difficulty).
    """
    entry           = models.ForeignKey(LexicalEntry, on_delete=models.CASCADE,
                                        related_name="sentences")
    label           = models.CharField(max_length=300)
    tree            = models.TextField()                     # raw GF tree string
    pattern         = models.JSONField(default=dict)        # GrammarPattern fields
    linearizations  = models.JSONField(default=dict)        # {lang: text}

    class Meta:
        unique_together = [("entry", "tree")]

    def __str__(self):
        return f"{self.entry.word} – {self.label}"

    @property
    def difficulty(self) -> int:
        return self.pattern.get("difficulty", 1)


# ---------------------------------------------------------------------------
# 3. Session layer
# ---------------------------------------------------------------------------

class LessonSession(models.Model):
    """
    One user working through one source document in a specific language pair.

    A session persists across multiple exercise rounds.  Multiple sessions for
    the same (user, source_doc, target_lang) are allowed — they represent
    separate study sessions.

    Status lifecycle:
        pending      → Celery task submitted, no data yet
        words_ready  → Vocabulary + translations available; sentences still building
        complete     → All sentences generated; exercises ready
        failed       → Task failed; error stored in task result
    """
    STATUS_PENDING     = 'pending'
    STATUS_WORDS_READY = 'words_ready'
    STATUS_COMPLETE    = 'complete'
    STATUS_FAILED      = 'failed'
    STATUS_CHOICES = [
        (STATUS_PENDING,     'Pending'),
        (STATUS_WORDS_READY, 'Words ready'),
        (STATUS_COMPLETE,    'Complete'),
        (STATUS_FAILED,      'Failed'),
    ]

    user        = models.ForeignKey(User, on_delete=models.CASCADE,
                                    related_name="lesson_sessions")
    source_doc  = models.ForeignKey(SourceDocument, on_delete=models.CASCADE,
                                    related_name="sessions")
    source_lang = models.CharField(max_length=10)
    target_lang = models.CharField(max_length=10)
    status      = models.CharField(max_length=20, choices=STATUS_CHOICES,
                                   default=STATUS_PENDING, db_index=True)
    # Celery task ID — used to query task progress / error from the result backend
    task_id     = models.CharField(max_length=255, blank=True, db_index=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return (f"{self.user.username}: {self.source_doc.title} "
                f"[{self.source_lang}→{self.target_lang}] #{self.pk}")


class LessonWord(models.Model):
    """
    Junction between a LessonSession and a LexicalEntry.

    Carries source-document-specific data: how many times the primary GF
    function was matched in the source text (source_count), plus a snapshot of
    any alternates present in this source (their source_counts may differ from
    the global LexicalAlternate entries if they appear in other sources).
    """
    session     = models.ForeignKey(LessonSession, on_delete=models.CASCADE,
                                    related_name="lesson_words")
    entry       = models.ForeignKey(LexicalEntry, on_delete=models.CASCADE,
                                    related_name="lesson_words")
    source_count = models.PositiveIntegerField(default=0)
    # Per-source alternate counts: [{gf_function, source_count}, ...]
    alternate_counts = models.JSONField(default=list)

    class Meta:
        unique_together = [("session", "entry")]

    def __str__(self):
        return f"{self.session} — {self.entry.word} (×{self.source_count})"


# ---------------------------------------------------------------------------
# 4. Skill tracking
# ---------------------------------------------------------------------------

class UserLanguageProfile(models.Model):
    """
    Per-user, per-language-pair skill state.

    'skill_data' is the serialized SkillProfile from translator/skill.py.
    As the skill model evolves (e.g. toward per-node FSRS tracking) the JSON
    schema can be extended without a migration — old sessions simply don't have
    the newer keys.

    skill_data schema (current):
    {
      "attempts":             [int * 5],   # per difficulty level 1–5
      "correct":              [int * 5],
      "vocab_seen":           [str, ...],  # gf_function strings
      "exercises_completed":  [int * 5],
      "node_attempts":        {node_key: int},   # fine-grained tracking
      "node_correct":         {node_key: int},
    }

    Node keys follow the convention:
      "tense.TPres", "person.they_Pron", "vocab.battery_1_N", "polarity.PNeg", …
    """
    user        = models.ForeignKey(User, on_delete=models.CASCADE,
                                    related_name="language_profiles")
    source_lang = models.CharField(max_length=10)
    target_lang = models.CharField(max_length=10)
    skill_data  = models.JSONField(default=dict)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("user", "source_lang", "target_lang")]

    def __str__(self):
        return (f"{self.user.username}: "
                f"{self.source_lang}→{self.target_lang}")


# ---------------------------------------------------------------------------
# 5. Exercise log
# ---------------------------------------------------------------------------

class ExerciseAttempt(models.Model):
    """
    One recorded exercise attempt by a user.

    Stores enough information to reconstruct what was asked, what was answered,
    and the grammatical context — enabling per-pattern analytics without
    re-joining to GeneratedSentence.
    """
    EXERCISE_TYPES = [
        ("word_translation_mc",  "Word translation (MC)"),
        ("sentence_translation", "Sentence translation (open)"),
        ("sentence_mc",          "Sentence translation (MC)"),
        ("fill_blank",           "Fill in the blank"),
        ("conjugation_table",    "Conjugation table"),
    ]

    user            = models.ForeignKey(User, on_delete=models.CASCADE,
                                        related_name="exercise_attempts")
    session         = models.ForeignKey(LessonSession, on_delete=models.SET_NULL,
                                        null=True, blank=True,
                                        related_name="attempts")
    exercise_type   = models.CharField(max_length=40, choices=EXERCISE_TYPES)
    difficulty      = models.PositiveSmallIntegerField()        # 1–5
    # Grammar pattern snapshot (GrammarPattern fields, may be empty for vocab MC)
    pattern         = models.JSONField(default=dict)
    # Vocabulary context
    gf_function     = models.CharField(max_length=200, blank=True)
    gf_cat          = models.CharField(max_length=20, blank=True)
    # Exercise content
    prompt          = models.TextField()
    prompt_lang     = models.CharField(max_length=10)
    target_lang     = models.CharField(max_length=10)
    correct_answer  = models.TextField()
    user_answer     = models.TextField(blank=True)
    is_correct      = models.BooleanField()
    # Timing (null = not measured)
    response_time_ms = models.PositiveIntegerField(null=True, blank=True)
    created_at      = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "target_lang", "created_at"]),
            models.Index(fields=["gf_function"]),
        ]

    def __str__(self):
        status = "✓" if self.is_correct else "✗"
        return f"{status} {self.user.username}: {self.exercise_type} [{self.difficulty}]"
