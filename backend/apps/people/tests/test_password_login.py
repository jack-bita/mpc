"""apps/people/tests/test_password_login.py — the owner and managers log in with a password, through django-allauth
(AUTH-3; 03 §5.9, §5.10; ADR-0038).

The app calls allauth's JSON routes for the browser, under /_allauth/browser/v1/, and only those the app needs
(apps/people/api/password_urls.py). A login starts a Django session, kept in a cookie page scripts can't read; every
change a browser sends carries the CSRF token, so another website can't log a person in or out in their name.

    POST   auth/login      an email and a password       200, a session; a wrong password 400
    GET    auth/session    who is logged in              200; nobody 401
    DELETE auth/session    log out                       401: the session is gone
    POST   auth/signup     anything                      404: nobody signs up

Fake data only: the repo is public (03 §10).
"""

import pytest
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.test import Client, RequestFactory

from apps.people.accounts import AccountAdapter
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


def csrf_token(client: Client) -> str:
    # The CSRF token, as the app gets it: from the `csrftoken` cookie, which every allauth route hands out. The app
    # sends it back in the X-CSRFToken header; another website can't read our cookies, so it can't send the header.
    client.get(SESSION)
    return client.cookies["csrftoken"].value


def log_in(client: Client, **sent: str) -> int:
    answer = client.post(LOGIN, sent, content_type="application/json", HTTP_X_CSRFTOKEN=csrf_token(client))
    return answer.status_code


def test_login_by_email(manager: User) -> None:
    client = Client(enforce_csrf_checks=True)
    assert client.get(SESSION).status_code == 401  # nobody yet

    assert log_in(client, email="meneja@example.com", password="not-the-password") == 400
    assert client.get(SESSION).status_code == 401

    assert log_in(client, email="meneja@example.com", password=PASSWORD) == 200
    answer = client.get(SESSION)
    assert answer.status_code == 200
    assert answer.json()["data"]["user"]["id"] == str(manager.pk)


def test_login_needs_csrf(manager: User) -> None:
    # A real browser's visit, which the test client checks only when asked. Without the token, another website could
    # log the phone in to an account of its choosing, and watch what the person then types.
    client = Client(enforce_csrf_checks=True)
    answer = client.post(LOGIN, {"email": "meneja@example.com", "password": PASSWORD}, content_type="application/json")
    assert answer.status_code == 403
    assert client.get(SESSION).status_code == 401


def test_logout_ends_session(manager: User) -> None:
    client = Client(enforce_csrf_checks=True)
    assert log_in(client, email="meneja@example.com", password=PASSWORD) == 200

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


@pytest.mark.parametrize("password", ["babamfano", "+255712345678"])
def test_password_too_like_the_person_is_refused(password: str) -> None:
    # Our User has no username, first or last name, the attributes Django's check looks at by default: it is told
    # ours (AUTH_PASSWORD_VALIDATORS), so a person's name or phone number is no password.
    baba = User.objects.create_user(full_name="Baba Mfano", phone="+255712345678")
    with pytest.raises(ValidationError) as refused:
        validate_password(password, baba)
    assert "password_too_similar" in [error.code for error in refused.value.error_list]
