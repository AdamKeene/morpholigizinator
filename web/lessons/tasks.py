"""
Celery tasks for lesson building.

Two-phase pipeline
------------------
Phase 1 — quick_word_list (~15-30s)
    Extract keywords → semantic expansion → GF sense resolution → bare-word
    translations.  Saves preliminary LexicalEntry rows (no sentences) and
    transitions the LessonSession to 'words_ready' so the client can show
    the vocabulary list immediately.

Phase 2 — build_lesson (~30-120s)
    Full sentence generation against Parse.pgf.  Updates the existing
    LexicalEntry rows with GeneratedSentence children and transitions the
    session to 'complete'.

Broker configuration
--------------------
Development (no Redis):
    CELERY_BROKER_URL = 'sqla+sqlite:///celery_broker.sqlite3'
    CELERY_RESULT_BACKEND = 'django-db'

Production:
    CELERY_BROKER_URL = 'redis://localhost:6379/0'
    CELERY_RESULT_BACKEND = 'django-db'   # or 'redis://...'

Start a worker from web/:
    celery -A web worker -l info
"""

import logging

from celery import shared_task
from django.contrib.auth.models import User
from django.db import transaction

from .models import LessonSession, SourceDocument
from .services import store_lesson

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=1, default_retry_delay=10)
def build_lesson_task(
    self,
    session_id: int,
    user_id: int,
    doc_id: int,
    source_lang: str,
    target_lang: str,
):
    """
    Build a lesson for the given session in two phases.

    Parameters mirror the LessonSession row so the task is fully
    self-contained and can be retried after a worker restart.
    """
    session = LessonSession.objects.get(pk=session_id)
    user    = User.objects.get(pk=user_id)
    doc     = SourceDocument.objects.get(pk=doc_id)
    text    = doc.raw_text
    target_langs = [target_lang, source_lang] if target_lang != source_lang else [source_lang]

    try:
        # ------------------------------------------------------------------
        # Phase 1: fast vocabulary resolution (no sentences)
        # ------------------------------------------------------------------
        from translator.keywords import extract_keywords
        from translator.expansion import semantic_expansion
        from translator import quick_word_list
        from translator.config import LANG_CONFIG

        logger.info("[session %d] phase 1: extracting keywords", session_id)
        from document_loader import chunk_by_topic
        chunks = chunk_by_topic(text)
        keywords, _ = extract_keywords(chunks, source_lang)

        # Semantic expansion with fastText (skips gracefully if vectors missing)
        import os
        vec_path = LANG_CONFIG[source_lang].get("fasttext_vec", "")
        if os.path.exists(vec_path):
            from translator.config import TOP_N_SIMILAR
            vocab = semantic_expansion(keywords, source_lang, TOP_N_SIMILAR)
        else:
            vocab = dict(keywords)

        logger.info("[session %d] phase 1: resolving %d words", session_id, len(vocab))
        preliminary = quick_word_list(vocab, source_lang, target_langs)

        _store_preliminary(session, preliminary)
        session.status = LessonSession.STATUS_WORDS_READY
        session.save(update_fields=["status"])
        logger.info("[session %d] words_ready (%d entries)", session_id, len(preliminary))

        # ------------------------------------------------------------------
        # Phase 2: full sentence generation
        # ------------------------------------------------------------------
        logger.info("[session %d] phase 2: generating sentences", session_id)
        from translator import build_lesson
        full_entries = build_lesson(vocab, text, source_lang, target_langs)

        store_lesson(user, doc, full_entries, source_lang, target_lang)
        session.status = LessonSession.STATUS_COMPLETE
        session.save(update_fields=["status"])
        logger.info("[session %d] complete (%d entries)", session_id, len(full_entries))

    except Exception as exc:
        logger.exception("[session %d] task failed: %s", session_id, exc)
        session.status = LessonSession.STATUS_FAILED
        session.save(update_fields=["status"])
        raise self.retry(exc=exc)

    return {"session_id": session_id, "word_count": len(full_entries)}


@transaction.atomic
def _store_preliminary(session: LessonSession, entries: list) -> None:
    """
    Save quick_word_list entries as LexicalEntry rows (no GeneratedSentence yet).

    Called between phases so the client can display words immediately.
    Uses update_or_create so a retry of this task is idempotent.
    """
    from .models import LexicalEntry, LexicalAlternate, LessonWord

    for entry in entries:
        word        = entry["word"]
        gf_function = entry.get("gf_function") or ""
        gf_cat      = entry.get("gf_cat") or ""
        in_wordnet  = bool(entry.get("in_wordnet"))
        translations = entry.get("translations") or {}
        alternates   = entry.get("alternates") or []

        lex, _ = LexicalEntry.objects.update_or_create(
            word=word,
            gf_function=gf_function,
            defaults={
                "gf_cat":      gf_cat,
                "in_wordnet":  in_wordnet,
                "translations": translations,
            },
        )

        for alt in alternates:
            alt_fn = alt.get("gf_function", "")
            if alt_fn:
                LexicalAlternate.objects.update_or_create(
                    entry=lex,
                    gf_function=alt_fn,
                    defaults={"translations": alt.get("translations") or {}},
                )

        LessonWord.objects.get_or_create(
            session=session,
            entry=lex,
            defaults={"source_count": 0, "alternate_counts": []},
        )
