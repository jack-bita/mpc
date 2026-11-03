"""apps/people/api/password_urls.py — the password routes of the owner and managers: the few of django-allauth's
routes the app may call, mounted under /_allauth/browser/v1/ by config/urls.py (AUTH-3; 03 §5.10; ADR-0038).

allauth's own list (allauth.headless.urls) holds more than we use, and has no setting to leave a route out. Among them,
a logged-in person could add or change their own email or phone: the login names they give, set past the owner, the
phone cleaner and the audit trail (PPL-2). So only the routes below exist; any other address here answers 404, and a
route a newer allauth adds stays closed until a card lists it here. Each is allauth's own view, for the browser:
Django's session cookie, CSRF-checked (ADR-0038).

    GET    auth/session    who is logged in: 200, or 401 when nobody is
    DELETE auth/session    log out: the session ends at once
    POST   auth/login      log in with an email, or a phone written +255…, and a password

Not here: sign-up, closed to everyone (the owner adds people, PPL-2); a login by a code sent by email or SMS.
allauth answers in its own shape, not the API's one error shape (CORE-6): UI-5's forms read its codes.
"""

from allauth.headless.account.views import LoginView, SessionView
from allauth.headless.constants import Client
from django.urls import path

urlpatterns = [
    path("auth/session", SessionView.as_api_view(client=Client.BROWSER), name="password-session"),
    path("auth/login", LoginView.as_api_view(client=Client.BROWSER), name="password-login"),
]
