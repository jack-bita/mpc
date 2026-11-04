"""apps/people/api/auth_urls.py — the login routes of our own, mounted under /api/auth/ by config/urls.py (AUTH-4; 03
§5.10): PIN login on a shop's device. A password's login is allauth's own (apps/people/api/password_urls.py).
"""

from django.urls import path

from apps.people.api.views import PinLoginView

urlpatterns = [
    path("pin-login/", PinLoginView.as_view(), name="auth-pin-login"),
]
