"""apps/people/tests/test_password_login.py — the owner and managers log in with a password, through django-allauth
(AUTH-3; 03 §5.9, §5.10; ADR-0038).

The app calls allauth's JSON routes for the browser, under /_allauth/browser/v1/, and only those the app needs
(apps/people/api/password_urls.py). A login starts a Django session, kept in a cookie page scripts can't read; every
change a browser sends carries the CSRF token, so another website can't log a person in or out in their name.

    POST   auth/login      an email and a password       200, a session; a wrong password 400
    POST   auth/login      a phone (+255…) and a password    the same, by phone: most people have no email
    GET    auth/session    who is logged in              200; nobody 401
    DELETE auth/session    log out                       401: the session is gone
    POST   auth/signup     anything                      404: nobody signs up

Fake data only: the repo is public (03 §10).
"""

from unittest import mock

import pytest
from django.contrib.auth.hashers import MD5PasswordHasher
from django.contrib.auth.password_validation import validate_password
from django.core import mail
from django.core.exceptions import ValidationError
from django.test import Client, RequestFactory

from apps.people.accounts import AccountAdapter
from apps.people.api import password_urls
from apps.people.models import User

pytestmark = pytest.mark.django_db

# The routes, written out here rather than imported: they are a promise to the app, and a test that read them from the
# code would follow the code wherever it went.
LOGIN = "/_allauth/browser/v1/auth/login"
SESSION = "/_allauth/browser/v1/auth/session"
SIGNUP = "/_allauth/browser/v1/auth/signup"

PASSWORD = "mbegu-za-mahindi-2026"


@pytest.fixture
def manager() -> User:
    # A manager who has an email, as some do, with a password the superuser set in the admin until AUTH-6.
    return User.objects.create_user(full_name="Meneja Mfano", email="meneja@example.com", password=PASSWORD)


@pytest.fixture
def owner() -> User:
    # The owner, with a phone and no email, as most of the shop's people (ADR-0038). Typed as people say it; stored
    # as +255712345678 (apps/core/phones.py).
    return User.objects.create_user(full_name="Baba Mfano", phone="0712 345 678", password=PASSWORD)


def csrf_token(client: Client) -> str:
    # The CSRF token, as the app gets it: from the `csrftoken` cookie, which every allauth route hands out. The app
    # sends it back in the X-CSRFToken header; another website can't read our cookies, so it can't send the header.
    client.get(SESSION)
    return client.cookies["csrftoken"].value


def log_in(client: Client, **sent: str) -> tuple[int, list[str]]:
    # A login as the app sends it, JSON with the CSRF token. Its answer's status, and allauth's error codes, in its own
    # shape, not the API's (apps/people/api/password_urls.py): {"errors": [{"code": ...}, ...]}. UI-5's forms read them.
    answer = client.post(LOGIN, sent, content_type="application/json", HTTP_X_CSRFTOKEN=csrf_token(client))
    return answer.status_code, [error["code"] for error in answer.json().get("errors", [])]


def hashes_at_the_login(**sent: str) -> int:
    # How many times one login attempt hashes the password. Every hash passes through the hasher's `encode`, its check
    # included, and the test settings' hasher is MD5 (config/settings/test.py).
    with mock.patch.object(MD5PasswordHasher, "encode", autospec=True, side_effect=MD5PasswordHasher.encode) as hashing:
        Client().post(LOGIN, sent, content_type="application/json")
    return hashing.call_count


def test_login_takes_one_hash_whatever_is_typed(manager: User, owner: User) -> None:
    # The hash is the slow part of a login, so its count shows in how long the answer takes: the same count for a right
    # password, a wrong one and nobody at all tells a stranger nothing about who has an account, or which guess was
    # right.
    for name, known, unknown in (
        ("email", "meneja@example.com", "mgeni@example.com"),
        ("phone", "+255712345678", "+255712999999"),
    ):
        assert hashes_at_the_login(**{name: known, "password": PASSWORD}) == 1
        assert hashes_at_the_login(**{name: known, "password": "not-the-password"}) == 1
        assert hashes_at_the_login(**{name: unknown, "password": PASSWORD}) == 1


def test_login_by_email(manager: User) -> None:
    client = Client(enforce_csrf_checks=True)
    assert client.get(SESSION).status_code == 401  # nobody yet

    assert log_in(client, email="meneja@example.com", password="not-the-password") == (400, ["email_password_mismatch"])
    assert client.get(SESSION).status_code == 401

    assert log_in(client, email="meneja@example.com", password=PASSWORD) == (200, [])
    answer = client.get(SESSION)
    assert answer.status_code == 200
    assert answer.json()["data"]["user"]["id"] == str(manager.pk)


def test_login_by_email_any_case(manager: User) -> None:
    # Emails are stored in lower case (PPL-1); a phone's keyboard often starts with a capital letter.
    client = Client(enforce_csrf_checks=True)
    assert log_in(client, email="Meneja@Example.COM", password=PASSWORD) == (200, [])


def test_login_by_phone(owner: User) -> None:
    client = Client(enforce_csrf_checks=True)
    assert log_in(client, phone="+255712345678", password="not-the-password") == (400, ["phone_password_mismatch"])
    assert client.get(SESSION).status_code == 401

    assert log_in(client, phone="+255712345678", password=PASSWORD) == (200, [])
    answer = client.get(SESSION)
    assert answer.status_code == 200
    assert answer.json()["data"]["user"]["id"] == str(owner.pk)


def test_phone_login_needs_the_country_code(owner: User) -> None:
    # allauth's login takes a phone only as +255…: it refuses 0712… before asking us, so the app writes the number out
    # in full before it sends it (UI-5). A number our cleaner refuses has our code; an unknown one is answered as a
    # wrong password, so the login never tells a stranger who has an account here.
    client = Client(enforce_csrf_checks=True)
    assert log_in(client, phone="0712345678", password=PASSWORD) == (400, ["invalid_phone"])
    assert log_in(client, phone="+255123", password=PASSWORD) == (400, ["phone.invalid"])
    assert log_in(client, phone="+255754000000", password=PASSWORD) == (400, ["phone_password_mismatch"])
    assert client.get(SESSION).status_code == 401


def test_phone_login_sends_no_sms(owner: User, monkeypatch: pytest.MonkeyPatch) -> None:
    # No SMS, and no change to the person's phone: the hooks that would do either are allauth's own, which refuse
    # loudly; here they only note that something reached them.
    reached: list[str] = []
    for hook in ("send_verification_code_sms", "send_unknown_account_sms", "set_phone", "set_phone_verified"):
        monkeypatch.setattr(AccountAdapter, hook, lambda *args, _hook=hook, **kwargs: reached.append(_hook))

    client = Client(enforce_csrf_checks=True)
    assert log_in(client, phone="+255712345678", password="not-the-password") == (400, ["phone_password_mismatch"])
    assert log_in(client, phone="+255712345678", password=PASSWORD) == (200, [])
    assert reached == []
    assert mail.outbox == []


def test_wrong_passwords_count_per_phone(owner: User) -> None:
    # allauth counts a person's wrong passwords, 5 in 5 minutes, under their login name: for a phone, our adapter
    # adds it (apps/people/accounts.py). Without it, every phone login shared one count, and five wrong passwords for
    # Baba's phone would have locked the manager out too.
    meneja = User.objects.create_user(full_name="Meneja Mfano", phone="0754 111 222", password=PASSWORD)
    client = Client(enforce_csrf_checks=True)
    for _ in range(5):
        assert log_in(client, phone="+255712345678", password="not-the-password") == (400, ["phone_password_mismatch"])

    # Baba's own count is full: even the right password waits now.
    assert log_in(client, phone="+255712345678", password=PASSWORD) == (400, ["too_many_login_attempts"])

    # The manager's is her own.
    other = Client(enforce_csrf_checks=True)
    assert log_in(other, phone="+255754111222", password=PASSWORD) == (200, [])
    assert other.get(SESSION).json()["data"]["user"]["id"] == str(meneja.pk)


def test_login_needs_csrf(manager: User) -> None:
    # A real browser's visit, which the test client checks only when asked. Without the token, another website could
    # log the phone in to an account of its choosing, and watch what the person then types.
    client = Client(enforce_csrf_checks=True)
    answer = client.post(LOGIN, {"email": "meneja@example.com", "password": PASSWORD}, content_type="application/json")
    assert answer.status_code == 403
    assert client.get(SESSION).status_code == 401


def test_logout_ends_session(manager: User) -> None:
    client = Client(enforce_csrf_checks=True)
    assert log_in(client, email="meneja@example.com", password=PASSWORD) == (200, [])

    # Logging out is a change too: without the token, another website could log the person out.
    assert client.delete(SESSION).status_code == 403
    assert client.get(SESSION).status_code == 200

    assert client.delete(SESSION, HTTP_X_CSRFTOKEN=csrf_token(client)).status_code == 401
    assert client.get(SESSION).status_code == 401


def test_signup_closed() -> None:
    # The route doesn't exist: the owner adds people (PPL-2). The adapter refuses too, for any other way in that a
    # later allauth feature might open.
    client = Client()
    answer = client.post(SIGNUP, {"email": "mgeni@example.com", "password": PASSWORD}, content_type="application/json")
    assert answer.status_code == 404
    assert AccountAdapter().is_open_for_signup(RequestFactory().post(SIGNUP)) is False
    assert not User.objects.filter(email="mgeni@example.com").exists()


# allauth's own list has more than we mount, with no setting to leave one out, and a route a newer allauth adds must
# stay closed too (apps/people/api/password_urls.py). Among these, a logged-in person could change their own email or
# phone, past the owner, or log in by a code. Tried logged in, as that is who the worst of them would serve.
@pytest.mark.parametrize(
    "route",
    [
        "/_allauth/browser/v1/account/email",
        "/_allauth/browser/v1/account/phone",
        "/_allauth/browser/v1/account/password/change",
        "/_allauth/browser/v1/account/authenticators",
        "/_allauth/browser/v1/auth/code/request",
        "/_allauth/browser/v1/auth/code/confirm",
        "/_allauth/browser/v1/auth/email/verify",
        "/_allauth/browser/v1/auth/phone/verify",
        "/_allauth/browser/v1/auth/reauthenticate",
        "/_allauth/browser/v1/auth/provider/redirect",
        "/_allauth/browser/v1/auth/sessions",
        "/_allauth/browser/v1/config",
        "/_allauth/browser/v1/tokens/refresh",
        "/_allauth/app/v1/auth/login",
        "/accounts/login/",
        "/accounts/signup/",
        "/accounts/password/reset/",
    ],
)
def test_routes_not_on_our_list_do_not_exist(manager: User, route: str) -> None:
    client = Client()
    client.force_login(manager)
    assert client.get(route).status_code == 404
    assert client.post(route, {}, content_type="application/json").status_code == 404


def test_only_the_routes_on_our_list_are_mounted() -> None:
    # The list itself: adding a route must change this test too, so it is a decision someone looked at.
    assert {route.name for route in password_urls.urlpatterns} == {
        "password-session",
        "password-login",
        "password-reset-request",
        "password-reset",
    }


def test_switched_off_person_cannot_log_in(manager: User) -> None:
    # `is_active`, the switch on the person. Even with the right password: no session starts. Only someone who knows the
    # password can tell this apart from a wrong one, which still answers as a wrong one.
    User.objects.filter(pk=manager.pk).update(is_active=False)
    client = Client()
    assert log_in(client, email="meneja@example.com", password="not-the-password") == (400, ["email_password_mismatch"])
    assert log_in(client, email="meneja@example.com", password=PASSWORD)[0] == 401
    assert client.get(SESSION).status_code == 401


@pytest.mark.parametrize("password", ["babamfano", "+255712345678"])
def test_password_too_like_the_person_is_refused(password: str) -> None:
    # Our User has no username, first or last name, the attributes Django's check looks at by default: it is told
    # ours (AUTH_PASSWORD_VALIDATORS), so a person's name or phone number is no password.
    baba = User.objects.create_user(full_name="Baba Mfano", phone="+255712345678")
    with pytest.raises(ValidationError) as refused:
        validate_password(password, baba)
    assert "password_too_similar" in [error.code for error in refused.value.error_list]
