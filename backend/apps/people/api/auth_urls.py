"""apps/people/api/auth_urls.py — the login routes of our own, mounted under /api/auth/ by config/urls.py (AUTH-4; 03
§5.10): PIN login on a shop's device, "who is here?", and logout. A password's login is allauth's own
(apps/people/api/password_urls.py).
"""

from django.urls import path

from apps.people.api.views import LogoutView, MeViewSet, PinLoginView

urlpatterns = [
    path("pin-login/", PinLoginView.as_view(), name="auth-pin-login"),
    path("logout/", LogoutView.as_view(), name="auth-logout"),
    path("me/", MeViewSet.as_view({"get": "me"}), name="auth-me"),
]
