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
from django.contrib.auth.models import AnonymousUser
from django.http import HttpRequest, HttpResponse
from django.urls import URLPattern, path
from django.views.decorators.debug import sensitive_variables

from apps.people.api.pin_session import PIN_SESSION


# allauth ships no types, so mypy knows both base classes below only as `Any`, and strict mode refuses a class built on
# one: the library's missing types, not ours (pyproject.toml).
class PasswordSessionView(SessionView):  # type: ignore[misc]
    # allauth's own "am I logged in?", which answers with the person's name and email. A password's session asks it on
    # its owner's own phone. A PIN's badge sits on a shared laptop, and this route knows nothing of a badge's checks
    # (job_of_pin_session, apps/people/selectors.py), which need the device's key, a cookie sent only to /api/. So
    # someone with a copied badge, or the next person at an open laptop, would read them here. To this route a badge is
    # nobody: the app asks `me` instead. Logging out through this route still works, as it reads no one's details.
    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if PIN_SESSION in request.session:
            request.user = AnonymousUser()
        answer: HttpResponse = super().get(request, *args, **kwargs)
        return answer


class PasswordResetView(ResetPasswordView):  # type: ignore[misc]
    # allauth's own reset, which ends by answering with whoever is logged in. Juma, resetting his own password on a
    # laptop where Asha's badge is open, would read her id, name and email. To this route, as to PasswordSessionView
    # above, a badge is nobody: he gets the answer anyone not logged in gets. The reset itself doesn't change.
    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if PIN_SESSION in request.session:
            request.user = AnonymousUser()
        answer: HttpResponse = super().post(request, *args, **kwargs)
        return answer


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


def _route(address: str, view: Any, name: str) -> URLPattern:
    # allauth's view for the browser, with every variable hidden from Django's error reports, here and in everything it
    # calls: a server will log and send those reports (OPS-10), which list each function's variables when something
    # fails. Wrapped at the route, as allauth's own frames hold what was sent, and the library at the bottom of the hash
    # names the password `secret`, so hiding one by its name wouldn't do. A crash here shows its lines, only not its
    # values. The login's checker needs its own wrapper (PasswordBackend, apps/people/accounts.py).
    route: URLPattern = path(address, sensitive_variables()(view.as_api_view(client=Client.BROWSER)), name=name)
    return route


urlpatterns = [
    _route("auth/session", PasswordSessionView, "password-session"),
    _route("auth/login", LoginView, "password-login"),
    _route("auth/password/request", RequestPasswordResetView, "password-reset-request"),
    _route("auth/password/reset", PasswordResetView, "password-reset"),
    _route("account/password/change", ChangeOwnPasswordView, "password-change"),
]
