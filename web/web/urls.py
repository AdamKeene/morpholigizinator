"""
URL configuration for web project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import include, path
from lessons import page_views

urlpatterns = [
    path("admin/",  admin.site.urls),
    path("api/",    include("lessons.urls")),

    # HTML pages
    path("",                            page_views.home,          name="page-home"),
    path("login/",                      page_views.login_view,    name="page-login"),
    path("logout/",                     page_views.logout_view,   name="page-logout"),
    path("register/",                   page_views.register_view, name="page-register"),
    path("sessions/",                   page_views.sessions_list, name="page-sessions"),
    path("sessions/<int:session_id>/",  page_views.session_view,  name="page-session"),
]
