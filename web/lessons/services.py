"""
Data-access helpers that sit between Django views and the morpholigizinator
pipeline.  All database writes go through these functions so the models stay
clean and the pipeline stays independent of Django.

Public API
----------
store_lesson(user, source_doc, build_lesson_output, source_lang, target_lang)
    → LessonSession

get_or_create_profile(user, source_lang, target_lang)
    → UserLanguageProfile

record_attempt(user, session, exercise, is_correct, response_time_ms=None)
    → ExerciseAttempt

load_skill_profile(user, source_lang, target_lang)
    → translator.skill.SkillProfile

save_skill_profile(user, source_lang, target_lang, profile)
    → None
"""

import dataclasses
from typing import Optional

from django.contrib.auth.models import User
from django.db import transaction

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


# ---------------------------------------------------------------------------
# Lesson ingestion
# ---------------------------------------------------------------------------

@transaction.atomic
def store_lesson(
    user: User,
    source_doc: SourceDocument,
    build_lesson_output: list,
    source_lang: str,
    target_lang: str,
) -> LessonSession:
    """
    Persist the output of translator.generator.build_lesson() to the database.

    - Upserts LexicalEntry / LexicalAlternate / GeneratedSentence rows (shared
      across sessions — same GF function → same rows).
    - Creates a new LessonSession and LessonWord rows for this session.

    Parameters
    ----------
    user               : the Django User requesting the lesson
    source_doc         : SourceDocument the lesson was built from
    build_lesson_output: list of entry dicts from build_lesson()
    source_lang        : ISO code of the source/prompt language
    target_lang        : primary target language for this session

    Returns
    -------
    The newly created LessonSession.
    """
    session = LessonSession.objects.create(
        user=user,
        source_doc=source_doc,
        source_lang=source_lang,
        target_lang=target_lang,
    )

    for entry_dict in build_lesson_output:
        word        = entry_dict["word"]
        gf_function = entry_dict.get("gf_function") or ""
        gf_cat      = entry_dict.get("gf_cat") or ""
        in_wordnet  = bool(entry_dict.get("in_wordnet"))
        translations = entry_dict.get("translations") or {}
        source_count = entry_dict.get("source_count", 0)
        alternates   = entry_dict.get("alternates") or []
        sentences    = entry_dict.get("sentences") or []

        # --- LexicalEntry (upsert) ---
        lex_entry, _ = LexicalEntry.objects.update_or_create(
            word=word,
            gf_function=gf_function,
            defaults={
                "gf_cat":      gf_cat,
                "in_wordnet":  in_wordnet,
                "translations": translations,
            },
        )

        # --- LexicalAlternate rows (upsert) ---
        for alt in alternates:
            alt_fn = alt.get("gf_function", "")
            if not alt_fn:
                continue
            LexicalAlternate.objects.update_or_create(
                entry=lex_entry,
                gf_function=alt_fn,
                defaults={"translations": alt.get("translations") or {}},
            )

        # --- GeneratedSentence rows (upsert by tree string, merge lins) ---
        # Linearizations are merged rather than overwritten so that rows
        # accumulated across multiple (source_lang, target_lang) sessions
        # build up a complete multilingual cache over time.  A user pair
        # en→de stores {en, de}; a later es→de session for the same word
        # adds es without losing the existing en lin.
        for sent in sentences:
            tree = sent.get("tree", "")
            if not tree:
                continue
            lins = {k: v for k, v in sent.items()
                    if k not in ("label", "tree", "pattern")}
            gs, created = GeneratedSentence.objects.get_or_create(
                entry=lex_entry,
                tree=tree,
                defaults={
                    "label":          sent.get("label", ""),
                    "pattern":        sent.get("pattern") or {},
                    "linearizations": lins,
                },
            )
            if not created:
                merged = {**gs.linearizations, **lins}
                if merged != gs.linearizations:
                    gs.linearizations = merged
                    gs.save(update_fields=["linearizations"])

        # --- LessonWord (this session's copy with source_count) ---
        alternate_counts = [
            {"gf_function": a.get("gf_function", ""),
             "source_count": a.get("source_count", 0)}
            for a in alternates
        ]
        LessonWord.objects.create(
            session=session,
            entry=lex_entry,
            source_count=source_count,
            alternate_counts=alternate_counts,
        )

    return session


# ---------------------------------------------------------------------------
# Skill profile
# ---------------------------------------------------------------------------

def get_or_create_profile(
    user: User,
    source_lang: str,
    target_lang: str,
) -> UserLanguageProfile:
    profile, _ = UserLanguageProfile.objects.get_or_create(
        user=user,
        source_lang=source_lang,
        target_lang=target_lang,
        defaults={"skill_data": _default_skill_data()},
    )
    return profile


def load_skill_profile(user: User, source_lang: str, target_lang: str):
    """Return a translator.skill.SkillProfile hydrated from the database."""
    from translator.skill import SkillProfile  # deferred: Django-independent

    db_profile = get_or_create_profile(user, source_lang, target_lang)
    data = db_profile.skill_data

    # Normalise node_data entries (forward-compat with older stored profiles)
    raw_nodes = data.get("node_data", {})
    for entry in raw_nodes.values():
        for k in ("attempts_r", "correct_r", "attempts_p", "correct_p"):
            entry.setdefault(k, 0)

    return SkillProfile(
        attempts=data.get("attempts", [0] * 5),
        correct=data.get("correct", [0] * 5),
        vocab_seen=data.get("vocab_seen", []),
        exercises_completed=data.get("exercises_completed", [0] * 5),
        node_data=raw_nodes,
    )


def save_skill_profile(
    user: User,
    source_lang: str,
    target_lang: str,
    profile,  # translator.skill.SkillProfile
) -> None:
    """Persist a translator.skill.SkillProfile back to the database."""
    # Exclude persistence-binding fields (user_id, db_path) that are
    # SkillProfile instance metadata, not learner data.
    _SKIP = {"user_id", "db_path"}
    db_profile = get_or_create_profile(user, source_lang, target_lang)
    db_profile.skill_data = {
        k: v for k, v in dataclasses.asdict(profile).items() if k not in _SKIP
    }
    db_profile.save(update_fields=["skill_data", "updated_at"])


# ---------------------------------------------------------------------------
# Exercise recording
# ---------------------------------------------------------------------------

def record_attempt(
    user: User,
    session: Optional[LessonSession],
    exercise,       # translator.exercise.Exercise
    is_correct: bool,
    response_time_ms: Optional[int] = None,
    user_answer: str = "",
) -> ExerciseAttempt:
    """
    Persist one exercise attempt and update skill counters.

    Updates both:
      - The coarse per-difficulty-level counters on SkillProfile
      - The per-node counters for every grammar node exercised by this pattern
    """
    target_lang = exercise.target_lang
    source_lang = exercise.prompt_lang
    exercise_type = exercise.exercise_type.value

    attempt = ExerciseAttempt.objects.create(
        user=user,
        session=session,
        exercise_type=exercise_type,
        difficulty=exercise.difficulty,
        pattern=exercise.metadata.get("pattern") or {},
        gf_function=exercise.metadata.get("gf_function") or "",
        gf_cat=exercise.metadata.get("gf_cat") or "",
        prompt=exercise.prompt,
        prompt_lang=source_lang,
        target_lang=target_lang,
        correct_answer=exercise.correct,
        user_answer=user_answer,
        is_correct=is_correct,
        response_time_ms=response_time_ms,
    )

    # Update SkillProfile — both coarse and per-node counters
    profile = load_skill_profile(user, source_lang, target_lang)
    profile.record_attempt(exercise.difficulty, is_correct)

    mode = _exercise_mode(exercise_type)
    pattern_dict = exercise.metadata.get("pattern") or {}
    if pattern_dict:
        from translator.nodes import pattern_to_node_keys
        for node_key in pattern_to_node_keys(pattern_dict, target_lang):
            profile.record_node_attempt(node_key, is_correct, mode)

    save_skill_profile(user, source_lang, target_lang, profile)

    return attempt


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Exercise types that test productive knowledge (generate the form)
# vs. receptive knowledge (recognise the correct form).
_PRODUCTIVE_EXERCISE_TYPES = frozenset({
    "sentence_translation",
    "fill_blank",
    "conjugation_table",
})


def _exercise_mode(exercise_type: str) -> str:
    """Return 'p' (productive) or 'r' (receptive) for this exercise type."""
    return "p" if exercise_type in _PRODUCTIVE_EXERCISE_TYPES else "r"


def _default_skill_data() -> dict:
    return {
        "attempts":            [0] * 5,
        "correct":             [0] * 5,
        "vocab_seen":          [],
        "exercises_completed": [0] * 5,
        # Per-node tracking: {node_key: {attempts_r, correct_r, attempts_p, correct_p}}
        "node_data":           {},
    }
