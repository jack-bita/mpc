"""apps/people/api/password_urls.py — the password routes of the owner and managers: the few of django-allauth's
routes the app may call, mounted under /_allauth/browser/v1/ by config/urls.py (AUTH-3, AUTH-6; 03 §5.10; ADR-0038).

allauth's own list (allauth.headless.urls) holds more than we use, and has no setting to leave a route out. Among them,
a logged-in person could add or change their own email or phone: the login names they give, set past the owner, the
phone cleaner and the audit trail (PPL-2). So only the routes below exist; any other address here answers 404, and a
route a newer allauth adds stays closed until a card lists it here. Each is allauth's own view, for the browser:
Django's session cookie, CSRF-checked (ADR-0038).

    GET    auth/session    who is logged in: 200, or 401 when nobody is
    DELETE auth/session    log out: the session ends at once
    POST   auth/login      log in with an email, or a phone written +255…, and a password
    POST   auth/password/request   send a reset link to this email; the same answer whether or not anyone has it
    GET    auth/password/reset     is this link's key still good? (X-Password-Reset-Key)
    POST   auth/password/reset     set a new password with the link's key
    POST   account/password/change   choose a new password, with the current one: how a temporary one ends (AUTH-6)

Not here: sign-up, closed to everyone (the owner adds people, PPL-2); a login by a code sent by email or SMS.
allauth answers in its own shape, not the API's one error shape (CORE-6): UI-5's forms read its codes.

These routes aren't office routes, so a person with the "must change password" mark still reaches them: the mark closes
the office routes only (apps/people/selectors.py), and the change route below is the way out.
"""

from typing import Any

from allauth.headless.account.inputs import ChangePasswordInput
from allauth.headless.account.views import (
    ChangePasswordView,
    LoginView,
    RequestPasswordResetView,
    ResetPasswordView,
    SessionView,
)
from allauth.headless.constants import Client
from django.urls import path


# allauth ships no types, so mypy knows both base classes below only as `Any`, and strict mode refuses a class built on
# one: the library's missing types, not ours (pyproject.toml).
class ChangeOwnPasswordInput(ChangePasswordInput):  # type: ignore[misc]
    # allauth's own form asks for the current password only of a person who has one, so someone with none may set one
    # with no check at all. A PIN session reaches this route too (AUTH-4): at a shared laptop left open, anyone could
    # give a PIN-only worker a password, and log in as them from anywhere for good. A first password is the owner's to
    # set, face to face (ADR-0038), so the current one is always asked; a person with none has nothing that can match.
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["current_password"].required = True


class ChangeOwnPasswordView(ChangePasswordView):  # type: ignore[misc]
    # allauth's own route, with the form above. It keeps allauth's limit, 5 a minute per person, which wraps the base
    # class's `handle` (test_change_is_slowed_down pins it).
    input_class = ChangeOwnPasswordInput


urlpatterns = [
    path("auth/session", SessionView.as_api_view(client=Client.BROWSER), name="password-session"),
    path("auth/login", LoginView.as_api_view(client=Client.BROWSER), name="password-login"),
    path(
        "auth/password/request",
        RequestPasswordResetView.as_api_view(client=Client.BROWSER),
        name="password-reset-request",
    ),
    path("auth/password/reset", ResetPasswordView.as_api_view(client=Client.BROWSER), name="password-reset"),
    path("account/password/change", ChangeOwnPasswordView.as_api_view(client=Client.BROWSER), name="password-change"),
]
