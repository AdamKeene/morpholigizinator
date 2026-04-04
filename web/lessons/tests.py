"""
Tests for the morpholigizinator web layer.

Covers:
- Page views (auth, home, sessions, session detail)
- REST API endpoints (auth, documents, sessions, words, exercises, attempts, profile)
- Exercise serialisation (choices field, not distractors)
- _exercise_to_dict fix
"""

import json
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from .models import (
    ExerciseAttempt,
    LessonSession,
    LessonWord,
    LexicalEntry,
    SourceDocument,
    UserLanguageProfile,
)


# ============================================================
# Helpers
# ============================================================

def make_user(username="testuser", password="testpass123"):
    return User.objects.create_user(username=username, password=password)


def make_doc(source_lang="en"):
    return SourceDocument.objects.create(
        title="Test Doc", source_lang=source_lang, raw_text="The battery failed."
    )


def make_session(user, doc, source_lang="en", target_lang="de", status="complete"):
    return LessonSession.objects.create(
        user=user, source_doc=doc,
        source_lang=source_lang, target_lang=target_lang,
        status=status,
    )


def make_entry(word="battery", gf_function="battery_N", gf_cat="N",
               in_wordnet=True, translations=None):
    return LexicalEntry.objects.create(
        word=word,
        gf_function=gf_function,
        gf_cat=gf_cat,
        in_wordnet=in_wordnet,
        translations=translations or {"en": "battery", "de": "Batterie"},
    )


# ============================================================
# Page view tests
# ============================================================

class HomePageTest(TestCase):

    def test_home_redirects_unauthenticated(self):
        r = self.client.get(reverse("page-home"))
        self.assertRedirects(r, reverse("page-login"), fetch_redirect_response=False)

    def test_home_200_authenticated(self):
        make_user()
        self.client.login(username="testuser", password="testpass123")
        r = self.client.get(reverse("page-home"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "New lesson")


class LoginPageTest(TestCase):

    def test_get_login_page(self):
        r = self.client.get(reverse("page-login"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Log in")

    def test_login_valid_credentials_redirects(self):
        make_user()
        r = self.client.post(reverse("page-login"), {
            "username": "testuser", "password": "testpass123"
        })
        self.assertRedirects(r, reverse("page-home"), fetch_redirect_response=False)

    def test_login_invalid_credentials_shows_error(self):
        make_user()
        r = self.client.post(reverse("page-login"), {
            "username": "testuser", "password": "wrongpassword"
        })
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Invalid username or password")

    def test_login_redirects_if_already_logged_in(self):
        make_user()
        self.client.login(username="testuser", password="testpass123")
        r = self.client.get(reverse("page-login"))
        self.assertRedirects(r, reverse("page-home"), fetch_redirect_response=False)


class RegisterPageTest(TestCase):

    def test_get_register_page(self):
        r = self.client.get(reverse("page-register"))
        self.assertEqual(r.status_code, 200)

    def test_register_valid_creates_user_and_redirects(self):
        r = self.client.post(reverse("page-register"), {
            "username": "newuser",
            "email":    "new@example.com",
            "password":  "securepass1",
            "password2": "securepass1",
        })
        self.assertRedirects(r, reverse("page-home"), fetch_redirect_response=False)
        self.assertTrue(User.objects.filter(username="newuser").exists())

    def test_register_password_mismatch_shows_error(self):
        r = self.client.post(reverse("page-register"), {
            "username": "newuser",
            "password":  "securepass1",
            "password2": "different123",
        })
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "do not match")

    def test_register_duplicate_username_shows_error(self):
        make_user("existing")
        r = self.client.post(reverse("page-register"), {
            "username":  "existing",
            "password":  "securepass1",
            "password2": "securepass1",
        })
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "already taken")

    def test_register_short_password_shows_error(self):
        r = self.client.post(reverse("page-register"), {
            "username":  "newuser",
            "password":  "short",
            "password2": "short",
        })
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "8 characters")


class LogoutTest(TestCase):

    def test_logout_clears_session(self):
        make_user()
        self.client.login(username="testuser", password="testpass123")
        r = self.client.post(reverse("page-logout"))
        self.assertRedirects(r, reverse("page-login"), fetch_redirect_response=False)
        # Subsequent home request should redirect to login
        r2 = self.client.get(reverse("page-home"))
        self.assertRedirects(r2, reverse("page-login"), fetch_redirect_response=False)

    def test_logout_requires_post(self):
        make_user()
        self.client.login(username="testuser", password="testpass123")
        r = self.client.get(reverse("page-logout"))
        self.assertEqual(r.status_code, 405)


class SessionsPageTest(TestCase):

    def test_sessions_list_requires_login(self):
        r = self.client.get(reverse("page-sessions"))
        self.assertEqual(r.status_code, 302)

    def test_sessions_list_200_authenticated(self):
        make_user()
        self.client.login(username="testuser", password="testpass123")
        r = self.client.get(reverse("page-sessions"))
        self.assertEqual(r.status_code, 200)

    def test_session_detail_requires_login(self):
        r = self.client.get(reverse("page-session", kwargs={"session_id": 999}))
        self.assertEqual(r.status_code, 302)

    def test_session_detail_200_authenticated(self):
        user = make_user()
        self.client.login(username="testuser", password="testpass123")
        doc  = make_doc()
        sess = make_session(user, doc)
        r = self.client.get(reverse("page-session", kwargs={"session_id": sess.pk}))
        self.assertEqual(r.status_code, 200)
        # session_id must appear as JS variable
        self.assertContains(r, f"window.SESSION_ID = {sess.pk}")


# ============================================================
# API auth tests
# ============================================================

class ApiAuthTest(TestCase):

    def _api(self, method, url, data=None, auth_user=None):
        c = Client()
        if auth_user:
            c.force_login(auth_user)
        fn = getattr(c, method)
        kwargs = {"content_type": "application/json", "HTTP_ACCEPT": "application/json"}
        if data is not None:
            kwargs["data"] = json.dumps(data)
        return fn(url, **kwargs)

    def test_register_creates_user(self):
        r = self._api("post", "/api/auth/register/", {
            "username": "alice", "email": "a@b.com",
            "password": "securepass1", "password2": "securepass1",
        })
        self.assertEqual(r.status_code, 201)
        body = r.json()
        self.assertIn("token", body)
        self.assertEqual(body["username"], "alice")
        self.assertTrue(User.objects.filter(username="alice").exists())

    def test_register_password_mismatch_400(self):
        r = self._api("post", "/api/auth/register/", {
            "username": "bob", "password": "pass12345", "password2": "different",
        })
        self.assertEqual(r.status_code, 400)

    def test_login_returns_token(self):
        make_user("alice", "securepass1")
        r = self._api("post", "/api/auth/login/", {
            "username": "alice", "password": "securepass1",
        })
        self.assertEqual(r.status_code, 200)
        self.assertIn("token", r.json())

    def test_login_wrong_password_401(self):
        make_user("alice", "securepass1")
        r = self._api("post", "/api/auth/login/", {
            "username": "alice", "password": "wrong",
        })
        self.assertEqual(r.status_code, 401)

    def test_logout_204(self):
        from rest_framework.authtoken.models import Token
        user = make_user()
        Token.objects.create(user=user)   # token must exist for logout to delete it
        r = self._api("post", "/api/auth/logout/", auth_user=user)
        self.assertEqual(r.status_code, 204)


# ============================================================
# API document / session tests
# ============================================================

class ApiDocumentsTest(TestCase):

    def setUp(self):
        self.user = make_user()
        self.client.force_login(self.user)

    def _post_doc(self, payload):
        return self.client.post(
            "/api/documents/",
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_ACCEPT="application/json",
        )

    @patch("lessons.tasks.build_lesson_task")
    def test_upload_document_creates_session(self, mock_task):
        mock_task.delay.return_value = MagicMock(id="fake-task-id")
        r = self._post_doc({
            "title": "Test", "text": "hello world " * 30,
            "source_lang": "en", "target_lang": "de",
        })
        self.assertEqual(r.status_code, 202)
        body = r.json()
        self.assertIn("id", body)
        self.assertEqual(body["status"], "pending")
        self.assertTrue(LessonSession.objects.filter(pk=body["id"]).exists())
        mock_task.delay.assert_called_once()

    @patch("lessons.tasks.build_lesson_task")
    def test_upload_document_missing_text_400(self, _):
        r = self._post_doc({"title": "T", "source_lang": "en", "target_lang": "de"})
        self.assertEqual(r.status_code, 400)

    @patch("lessons.tasks.build_lesson_task")
    def test_upload_document_unsupported_lang_400(self, _):
        r = self._post_doc({
            "title": "T", "text": "hello " * 10,
            "source_lang": "en", "target_lang": "klingon",
        })
        self.assertEqual(r.status_code, 400)

    def test_list_documents_empty(self):
        r = self.client.get("/api/documents/", HTTP_ACCEPT="application/json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), [])

    def test_list_documents_requires_auth(self):
        c = Client()
        r = c.get("/api/documents/", HTTP_ACCEPT="application/json")
        self.assertEqual(r.status_code, 403)


class ApiSessionsTest(TestCase):

    def setUp(self):
        self.user = make_user()
        self.client.force_login(self.user)
        self.doc  = make_doc()
        self.sess = make_session(self.user, self.doc, status="complete")

    def test_list_sessions(self):
        r = self.client.get("/api/sessions/", HTTP_ACCEPT="application/json")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(len(body), 1)
        self.assertEqual(body[0]["id"], self.sess.pk)

    def test_session_detail(self):
        r = self.client.get(
            f"/api/sessions/{self.sess.pk}/", HTTP_ACCEPT="application/json"
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["status"], "complete")

    def test_session_detail_not_found_for_other_user(self):
        other = make_user("other")
        self.client.force_login(other)
        r = self.client.get(
            f"/api/sessions/{self.sess.pk}/", HTTP_ACCEPT="application/json"
        )
        self.assertEqual(r.status_code, 404)

    def test_session_words_pending_returns_202(self):
        pending_sess = make_session(self.user, self.doc, status="pending")
        r = self.client.get(
            f"/api/sessions/{pending_sess.pk}/words/", HTTP_ACCEPT="application/json"
        )
        self.assertEqual(r.status_code, 202)

    def test_session_words_complete_returns_word_list(self):
        entry = make_entry()
        LessonWord.objects.create(session=self.sess, entry=entry, source_count=2)
        r = self.client.get(
            f"/api/sessions/{self.sess.pk}/words/", HTTP_ACCEPT="application/json"
        )
        self.assertEqual(r.status_code, 200)
        words = r.json()
        self.assertEqual(len(words), 1)
        self.assertEqual(words[0]["entry"]["word"], "battery")
        self.assertEqual(words[0]["entry"]["translations"]["de"], "Batterie")

    def test_session_exercises_not_complete_returns_202(self):
        pending = make_session(self.user, self.doc, status="words_ready")
        r = self.client.get(
            f"/api/sessions/{pending.pk}/exercises/", HTTP_ACCEPT="application/json"
        )
        self.assertEqual(r.status_code, 202)

    def test_session_words_filter_known(self):
        e1 = make_entry("battery", "battery_N")
        e2 = make_entry("lamp",    "lamp_N",    translations={"en": "lamp", "de": "Lampe"})
        LessonWord.objects.create(session=self.sess, entry=e1, source_count=1)
        LessonWord.objects.create(session=self.sess, entry=e2, source_count=1)
        r = self.client.get(
            f"/api/sessions/{self.sess.pk}/words/?known=battery_N",
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(r.status_code, 200)
        words = r.json()
        # battery_N should be filtered out
        self.assertEqual(len(words), 1)
        self.assertEqual(words[0]["entry"]["gf_function"], "lamp_N")


# ============================================================
# API attempt tests
# ============================================================

class ApiAttemptTest(TestCase):

    def setUp(self):
        self.user = make_user()
        self.client.force_login(self.user)
        self.doc  = make_doc()
        self.sess = make_session(self.user, self.doc)

    def _attempt_payload(self, **overrides):
        payload = {
            "session_id":       self.sess.pk,
            "exercise_type":    "word_translation_mc",
            "difficulty":       2,
            "pattern":          {},
            "gf_function":      "battery_N",
            "gf_cat":           "N",
            "prompt":           "battery",
            "prompt_lang":      "en",
            "target_lang":      "de",
            "correct_answer":   "Batterie",
            "user_answer":      "Batterie",
            "is_correct":       True,
            "response_time_ms": 1200,
        }
        payload.update(overrides)
        return payload

    def test_submit_attempt_creates_record(self):
        r = self.client.post(
            "/api/attempts/",
            data=json.dumps(self._attempt_payload()),
            content_type="application/json",
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(r.status_code, 201)
        self.assertTrue(ExerciseAttempt.objects.filter(user=self.user).exists())

    def test_submit_attempt_missing_field_400(self):
        payload = self._attempt_payload()
        del payload["is_correct"]
        r = self.client.post(
            "/api/attempts/",
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(r.status_code, 400)

    def test_submit_attempt_wrong_session_404(self):
        r = self.client.post(
            "/api/attempts/",
            data=json.dumps(self._attempt_payload(session_id=99999)),
            content_type="application/json",
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(r.status_code, 404)

    def test_submit_attempt_updates_skill_profile(self):
        self.client.post(
            "/api/attempts/",
            data=json.dumps(self._attempt_payload()),
            content_type="application/json",
            HTTP_ACCEPT="application/json",
        )
        self.assertTrue(
            UserLanguageProfile.objects.filter(
                user=self.user, source_lang="en", target_lang="de"
            ).exists()
        )


# ============================================================
# Exercise serialisation — choices fix
# ============================================================

class ExerciseToDictTest(TestCase):
    """Verify _exercise_to_dict returns 'choices', not 'distractors'."""

    def test_word_mc_has_choices_key(self):
        from translator.exercise import Exercise, ExerciseType
        from lessons.views import _exercise_to_dict

        ex = Exercise(
            exercise_type=ExerciseType.WORD_TRANSLATION_MC,
            difficulty=2,
            prompt="battery",
            prompt_lang="en",
            target_lang="de",
            correct="Batterie",
            choices=["Batterie", "Lampe", "Tisch", "Stuhl"],
            metadata={"gf_function": "battery_N", "gf_cat": "N"},
        )
        d = _exercise_to_dict(ex)
        self.assertIn("choices", d)
        self.assertNotIn("distractors", d)
        self.assertIn("Batterie", d["choices"])

    def test_sentence_translation_choices_is_none(self):
        from translator.exercise import Exercise, ExerciseType
        from lessons.views import _exercise_to_dict

        ex = Exercise(
            exercise_type=ExerciseType.SENTENCE_TRANSLATION,
            difficulty=3,
            prompt="The battery is dead.",
            prompt_lang="en",
            target_lang="de",
            correct="Die Batterie ist leer.",
            choices=None,
            metadata={},
        )
        d = _exercise_to_dict(ex)
        self.assertIn("choices", d)
        self.assertIsNone(d["choices"])

    def test_sentence_mc_choices_shuffled(self):
        from translator.exercise import Exercise, ExerciseType
        from lessons.views import _exercise_to_dict

        choices = ["Die Batterie ist leer.", "Der Tisch ist groß.", "Ich esse Brot."]
        ex = Exercise(
            exercise_type=ExerciseType.SENTENCE_MC,
            difficulty=2,
            prompt="The battery is dead.",
            prompt_lang="en",
            target_lang="de",
            correct="Die Batterie ist leer.",
            choices=choices,
            metadata={},
        )
        d = _exercise_to_dict(ex)
        self.assertEqual(sorted(d["choices"]), sorted(choices))


# ============================================================
# Profile API
# ============================================================

class ApiProfileTest(TestCase):

    def setUp(self):
        self.user = make_user()
        self.client.force_login(self.user)

    def test_profile_404_when_none(self):
        r = self.client.get("/api/profile/en/de/", HTTP_ACCEPT="application/json")
        self.assertEqual(r.status_code, 404)

    def test_profile_200_when_exists(self):
        UserLanguageProfile.objects.create(
            user=self.user, source_lang="en", target_lang="de",
            skill_data={"attempts": [0]*5, "correct": [0]*5},
        )
        r = self.client.get("/api/profile/en/de/", HTTP_ACCEPT="application/json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["source_lang"], "en")
