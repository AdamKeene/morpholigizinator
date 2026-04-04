"""
REST API views for the morpholigizinator lesson system.

Endpoint summary
----------------
Auth
    POST   /api/auth/register/          Create account, return token
    POST   /api/auth/login/             Get token
    POST   /api/auth/logout/            Invalidate token

Documents
    GET    /api/documents/              List user's uploaded documents
    POST   /api/documents/              Upload document, start lesson build task
    GET    /api/documents/<id>/         Document detail

Sessions
    GET    /api/sessions/               List user's sessions
    GET    /api/sessions/<id>/          Session status (poll this for progress)
    GET    /api/sessions/<id>/words/    Word list (available from 'words_ready')
    GET    /api/sessions/<id>/exercises/ Adaptive exercise set (requires 'complete')

Attempts
    POST   /api/attempts/               Submit one exercise answer

Profile
    GET    /api/profile/<src>/<tgt>/    Skill profile for a language pair
"""

import logging

from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .models import (
    ExerciseAttempt,
    LessonSession,
    LessonWord,
    SourceDocument,
    UserLanguageProfile,
)
from .serializers import (
    ExerciseAttemptSerializer,
    LessonSessionSerializer,
    LessonWordSerializer,
    RegisterSerializer,
    SkillProfileSerializer,
    SourceDocumentSerializer,
)
from .services import load_skill_profile, record_attempt, save_skill_profile

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

@api_view(["POST"])
@permission_classes([AllowAny])
def register(request):
    """Create a new user account and return an auth token."""
    ser = RegisterSerializer(data=request.data)
    if not ser.is_valid():
        return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)
    user  = ser.save()
    token, _ = Token.objects.get_or_create(user=user)
    return Response({"token": token.key, "user_id": user.pk, "username": user.username},
                    status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([AllowAny])
def login(request):
    """Authenticate and return a token."""
    username = request.data.get("username", "")
    password = request.data.get("password", "")
    user = authenticate(request, username=username, password=password)
    if user is None:
        return Response({"detail": "Invalid credentials."}, status=status.HTTP_401_UNAUTHORIZED)
    token, _ = Token.objects.get_or_create(user=user)
    return Response({"token": token.key, "user_id": user.pk, "username": user.username})


@api_view(["POST"])
def logout(request):
    """Delete the user's auth token."""
    request.user.auth_token.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------

@api_view(["GET", "POST"])
def documents(request):
    if request.method == "GET":
        docs = SourceDocument.objects.filter(
            sessions__user=request.user
        ).distinct().order_by("-created_at")
        return Response(SourceDocumentSerializer(docs, many=True).data)

    # POST — upload a document and start building a lesson
    title       = request.data.get("title", "").strip()
    raw_text    = request.data.get("text", "").strip()
    source_lang = request.data.get("source_lang", "en").strip()
    target_lang = request.data.get("target_lang", "de").strip()
    imdb_id     = request.data.get("imdb_id", "").strip()

    if not raw_text:
        return Response({"detail": "text is required."}, status=status.HTTP_400_BAD_REQUEST)
    if not title:
        title = f"Document ({source_lang})"

    from translator.config import LANG_CONFIG
    for code in (source_lang, target_lang):
        if code not in LANG_CONFIG:
            return Response(
                {"detail": f"Unsupported language: '{code}'. "
                           f"Supported: {list(LANG_CONFIG)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

    # Get or create SourceDocument — same imdb_id+lang reuses the document
    # but always creates a fresh LessonSession.
    if imdb_id:
        doc, _ = SourceDocument.objects.get_or_create(
            imdb_id=imdb_id,
            source_lang=source_lang,
            defaults={"title": title, "raw_text": raw_text},
        )
    else:
        doc = SourceDocument.objects.create(
            title=title, source_lang=source_lang, raw_text=raw_text,
        )

    session = LessonSession.objects.create(
        user=request.user,
        source_doc=doc,
        source_lang=source_lang,
        target_lang=target_lang,
        status=LessonSession.STATUS_PENDING,
    )

    from .tasks import build_lesson_task
    task = build_lesson_task.delay(
        session_id=session.pk,
        user_id=request.user.pk,
        doc_id=doc.pk,
        source_lang=source_lang,
        target_lang=target_lang,
    )
    session.task_id = task.id
    session.save(update_fields=["task_id"])

    return Response(
        LessonSessionSerializer(session).data,
        status=status.HTTP_202_ACCEPTED,
    )


@api_view(["GET"])
def document_detail(request, doc_id):
    try:
        doc = SourceDocument.objects.get(pk=doc_id, sessions__user=request.user)
    except SourceDocument.DoesNotExist:
        return Response(status=status.HTTP_404_NOT_FOUND)
    return Response(SourceDocumentSerializer(doc).data)


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

@api_view(["GET"])
def sessions(request):
    qs = LessonSession.objects.filter(user=request.user).order_by("-created_at")
    return Response(LessonSessionSerializer(qs, many=True).data)


@api_view(["GET"])
def session_detail(request, session_id):
    """
    Poll this endpoint to track lesson build progress.

    Returns status, word_count, and (when complete) a link to /words/ and /exercises/.
    """
    try:
        session = LessonSession.objects.get(pk=session_id, user=request.user)
    except LessonSession.DoesNotExist:
        return Response(status=status.HTTP_404_NOT_FOUND)
    return Response(LessonSessionSerializer(session).data)


@api_view(["GET"])
def session_words(request, session_id):
    """
    Return the word list for a session.

    Available as soon as status == 'words_ready' (or 'complete').
    Each word entry includes translations and alternates.
    Sentences are present only after status == 'complete'.

    Query params:
        known=<gf_function>,<gf_function>,...  — filter out words the user knows
    """
    try:
        session = LessonSession.objects.get(pk=session_id, user=request.user)
    except LessonSession.DoesNotExist:
        return Response(status=status.HTTP_404_NOT_FOUND)

    if session.status == LessonSession.STATUS_PENDING:
        return Response(
            {"detail": "Vocabulary not ready yet. Poll /sessions/<id>/ for status."},
            status=status.HTTP_202_ACCEPTED,
        )

    known_fns = set(
        f.strip() for f in request.query_params.get("known", "").split(",") if f.strip()
    )

    words_qs = (
        session.lesson_words
        .select_related("entry")
        .prefetch_related("entry__alternates", "entry__sentences")
        .order_by("-source_count", "entry__word")
    )
    if known_fns:
        words_qs = words_qs.exclude(entry__gf_function__in=known_fns)

    return Response(LessonWordSerializer(words_qs, many=True).data)


@api_view(["GET"])
def session_exercises(request, session_id):
    """
    Return an adaptive exercise set for this session.

    Requires status == 'complete' (sentences must exist).

    Query params:
        n=<int>    — number of exercises (default 20)
        known=...  — comma-separated gf_functions to exclude
    """
    try:
        session = LessonSession.objects.get(pk=session_id, user=request.user)
    except LessonSession.DoesNotExist:
        return Response(status=status.HTTP_404_NOT_FOUND)

    if session.status != LessonSession.STATUS_COMPLETE:
        return Response(
            {"detail": f"Exercises not ready (status: {session.status}). "
                       "Poll /sessions/<id>/ for status."},
            status=status.HTTP_202_ACCEPTED,
        )

    n = int(request.query_params.get("n", 20))
    known_fns = set(
        f.strip() for f in request.query_params.get("known", "").split(",") if f.strip()
    )

    profile = load_skill_profile(request.user, session.source_lang, session.target_lang)

    # Build lesson entries from cached DB rows (no recomputation)
    words_qs = (
        session.lesson_words
        .select_related("entry")
        .prefetch_related("entry__alternates", "entry__sentences")
    )
    if known_fns:
        words_qs = words_qs.exclude(entry__gf_function__in=known_fns)

    lesson_entries = _words_to_lesson_entries(words_qs, session.target_lang)

    from translator.exercise import select_exercises
    exercises = select_exercises(
        lesson_entries,
        profile=profile,
        target_lang=session.target_lang,
        source_lang=session.source_lang,
        n=n,
    )

    return Response([_exercise_to_dict(ex) for ex in exercises])


# ---------------------------------------------------------------------------
# Attempts
# ---------------------------------------------------------------------------

@api_view(["POST"])
def submit_attempt(request):
    """
    Record one exercise attempt and update the user's skill profile.

    Expected body:
    {
        "session_id":       <int>,
        "exercise_type":    <str>,   # e.g. "word_translation_mc"
        "difficulty":       <int>,   # 1–5
        "pattern":          <dict>,  # GrammarPattern fields
        "gf_function":      <str>,
        "gf_cat":           <str>,
        "prompt":           <str>,
        "prompt_lang":      <str>,
        "target_lang":      <str>,
        "correct_answer":   <str>,
        "user_answer":      <str>,
        "is_correct":       <bool>,
        "response_time_ms": <int | null>
    }
    """
    data = request.data

    required = ["exercise_type", "difficulty", "prompt", "prompt_lang",
                "target_lang", "correct_answer", "user_answer", "is_correct"]
    missing = [f for f in required if f not in data]
    if missing:
        return Response({"detail": f"Missing fields: {missing}"},
                        status=status.HTTP_400_BAD_REQUEST)

    session = None
    if sid := data.get("session_id"):
        try:
            session = LessonSession.objects.get(pk=sid, user=request.user)
        except LessonSession.DoesNotExist:
            return Response({"detail": "Session not found."},
                            status=status.HTTP_404_NOT_FOUND)

    # Build a lightweight Exercise-like object for record_attempt()
    exercise = _ExerciseProxy(data)
    attempt = record_attempt(
        user=request.user,
        session=session,
        exercise=exercise,
        is_correct=bool(data["is_correct"]),
        response_time_ms=data.get("response_time_ms"),
        user_answer=str(data.get("user_answer", "")),
    )

    return Response(
        ExerciseAttemptSerializer(attempt).data,
        status=status.HTTP_201_CREATED,
    )


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

@api_view(["GET"])
def profile(request, source_lang, target_lang):
    """Return the serialized skill profile for a language pair."""
    try:
        p = UserLanguageProfile.objects.get(
            user=request.user, source_lang=source_lang, target_lang=target_lang
        )
    except UserLanguageProfile.DoesNotExist:
        return Response({"detail": "No profile yet for this language pair."},
                        status=status.HTTP_404_NOT_FOUND)
    return Response(SkillProfileSerializer(p).data)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _words_to_lesson_entries(words_qs, target_lang: str) -> list:
    """Convert ORM LessonWord rows back to the dict format build_lesson() returns."""
    entries = []
    for lw in words_qs:
        lex = lw.entry
        sents = [
            {**gs.linearizations, "tree": gs.tree, "label": gs.label, "pattern": gs.pattern}
            for gs in lex.sentences.all()
        ]
        alts = [
            {"gf_function": alt.gf_function, "translations": alt.translations}
            for alt in lex.alternates.all()
        ]
        entries.append({
            "word":          lex.word,
            "gf_function":   lex.gf_function,
            "gf_cat":        lex.gf_cat,
            "in_wordnet":    lex.in_wordnet,
            "translations":  lex.translations,
            "sentences":     sents,
            "alternates":    alts,
            "source_count":  lw.source_count,
            "source_examples": [],
        })
    return entries


def _exercise_to_dict(ex) -> dict:
    """Serialize a translator.exercise.Exercise to a plain dict for the API."""
    from translator.exercise import ExerciseType
    return {
        "exercise_type":  ex.exercise_type.value,
        "difficulty":     ex.difficulty,
        "prompt":         ex.prompt,
        "prompt_lang":    ex.prompt_lang,
        "target_lang":    ex.target_lang,
        "correct":        ex.correct,
        "choices":        ex.choices,
        "metadata":       ex.metadata,
    }


class _ExerciseProxy:
    """
    Thin proxy so record_attempt() (which expects a translator.exercise.Exercise)
    can work with raw POST data without requiring a full Exercise object.
    """
    def __init__(self, data: dict):
        from translator.exercise import ExerciseType
        self.exercise_type = ExerciseType(data["exercise_type"])
        self.difficulty    = int(data["difficulty"])
        self.prompt        = str(data["prompt"])
        self.prompt_lang   = str(data["prompt_lang"])
        self.target_lang   = str(data["target_lang"])
        self.correct       = str(data["correct_answer"])
        self.distractors   = []
        self.metadata      = {
            "pattern":     data.get("pattern") or {},
            "gf_function": data.get("gf_function", ""),
            "gf_cat":      data.get("gf_cat", ""),
        }
