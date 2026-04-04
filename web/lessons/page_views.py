"""
Template-based page views (return HTML, not JSON).

URL layout:
    /               → home (upload form if logged in, else redirect to login)
    /login/         → login form
    /logout/        → POST to log out
    /register/      → register form
    /sessions/      → list user's sessions
    /sessions/<id>/ → session page (word list + exercises)
"""

from django.contrib.auth import authenticate
from django.contrib.auth import login as _login
from django.contrib.auth import logout as _logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST


def home(request):
    if not request.user.is_authenticated:
        return redirect("page-login")
    return render(request, "lessons/home.html")


def login_view(request):
    if request.user.is_authenticated:
        return redirect("page-home")
    error = None
    if request.method == "POST":
        user = authenticate(
            request,
            username=request.POST.get("username", "").strip(),
            password=request.POST.get("password", ""),
        )
        if user:
            _login(request, user)
            next_url = request.POST.get("next") or request.GET.get("next") or "page-home"
            return redirect(next_url)
        error = "Invalid username or password."
    return render(request, "lessons/login.html", {"error": error})


@require_POST
def logout_view(request):
    _logout(request)
    return redirect("page-login")


def register_view(request):
    if request.user.is_authenticated:
        return redirect("page-home")
    errors = {}
    form_data = {}
    if request.method == "POST":
        username  = request.POST.get("username", "").strip()
        email     = request.POST.get("email", "").strip()
        password  = request.POST.get("password", "")
        password2 = request.POST.get("password2", "")
        form_data = {"username": username, "email": email}

        if not username:
            errors["username"] = "Username is required."
        elif User.objects.filter(username=username).exists():
            errors["username"] = "That username is already taken."

        if len(password) < 8:
            errors["password"] = "Password must be at least 8 characters."
        elif password != password2:
            errors["password2"] = "Passwords do not match."

        if not errors:
            user = User.objects.create_user(
                username=username, password=password, email=email
            )
            _login(request, user)
            return redirect("page-home")

    return render(request, "lessons/register.html", {"errors": errors, "form_data": form_data})


@login_required(login_url="/login/")
def sessions_list(request):
    return render(request, "lessons/sessions.html")


@login_required(login_url="/login/")
def session_view(request, session_id):
    return render(request, "lessons/session.html", {"session_id": session_id})
