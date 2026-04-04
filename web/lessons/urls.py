from django.urls import path
from . import views

urlpatterns = [
    # Auth
    path("auth/register/",  views.register,        name="auth-register"),
    path("auth/login/",     views.login,            name="auth-login"),
    path("auth/logout/",    views.logout,           name="auth-logout"),

    # Documents
    path("documents/",              views.documents,       name="documents"),
    path("documents/<int:doc_id>/", views.document_detail, name="document-detail"),

    # Sessions
    path("sessions/",                                  views.sessions,          name="sessions"),
    path("sessions/<int:session_id>/",                 views.session_detail,    name="session-detail"),
    path("sessions/<int:session_id>/words/",           views.session_words,     name="session-words"),
    path("sessions/<int:session_id>/exercises/",       views.session_exercises, name="session-exercises"),

    # Attempts
    path("attempts/", views.submit_attempt, name="submit-attempt"),

    # Profile
    path("profile/<str:source_lang>/<str:target_lang>/", views.profile, name="profile"),
]
