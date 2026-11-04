"""apps/people/tests/test_password_reset.py — someone who has an email can get back in with a link sent to it (AUTH-3;
03 §5.9; ADR-0038). Anyone else asks the owner, who sets a temporary password face to face (AUTH-6).

    POST auth/password/request   an email        200 whether or not anyone has it; a link goes to a known one only
    GET  auth/password/reset     the link's key  200 while it is good
    POST auth/password/reset     key + password  401: done, and not logged in; the old password and old sessions end

The key in the link sits after the #, which a browser never sends to a server. Fake data only: the repo is public
(03 §10).
"""

from datetime import datetime, timedelta
from unittest import mock

import pytest
from allauth.account.models import EmailAddress
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core import mail
from django.test import Client
from pytest_django import Settings

from apps.people.models import User

pytestmark = pytest.mark.django_db

LOGIN = "/_allauth/browser/v1/auth/login"
SESSION = "/_allauth/browser/v1/auth/session"
REQUEST = "/_allauth/browser/v1/auth/password/request"
RESET = "/_allauth/browser/v1/auth/password/reset"

EMAIL = "meneja@example.com"
NEW_EMAIL = "meneja.mpya@example.com"
PHONE = "+255712345678"
PASSWORD = "mbegu-za-mahindi-2026"
NEW_PASSWORD = "mbolea-ya-kupandia-2027"
JSON = "application/json"


@pytest.fixture
def manager() -> User:
    return User.objects.create_user(full_name="Meneja Mfano", email=EMAIL, phone=PHONE, password=PASSWORD)


def post(client: Client, path: str, **sent: str) -> tuple[int, list[str]]:
    # One request, as the app sends it. Its status, and allauth's error codes, in its own shape.
    answer = client.post(path, sent, content_type=JSON)
    return answer.status_code, [error["code"] for error in answer.json().get("errors", [])]


def key_from_the_email() -> str:
    # The key, from the link in the last email, as the app reads it from the address bar: after the #.
    [link] = [word for word in mail.outbox[-1].body.split() if "/password-reset#" in word]
    return link.partition("#")[2]


def test_password_reset_by_email(manager: User) -> None:
    client = Client()
    assert post(client, REQUEST, email=EMAIL) == (200, [])

    # The link goes to the person's own email, opens the app at the address the request came to, and holds the key
    # after the #, so no server's log ever sees it.
    [email] = mail.outbox
    assert email.to == [EMAIL]
    assert "http://testserver/password-reset#" in email.body
    key = key_from_the_email()
    assert client.get(RESET, headers={"X-Password-Reset-Key": key}).status_code == 200

    # Done, and not logged in: they log in with the new password, as anywhere else.
    assert post(client, RESET, key=key, password=NEW_PASSWORD) == (401, [])
    assert post(client, LOGIN, email=EMAIL, password=PASSWORD) == (400, ["email_password_mismatch"])
    assert post(client, LOGIN, email=EMAIL, password=NEW_PASSWORD) == (200, [])
    # Their phone logs in with it too: one person, one password (D12).
    assert post(Client(), LOGIN, phone=PHONE, password=NEW_PASSWORD) == (200, [])


def test_password_reset_with_no_phone() -> None:
    # An email and no phone, as the superuser has: a person holds only some of the names they could log in by.
    User.objects.create_user(full_name="Msimamizi Mfano", email=EMAIL, password=PASSWORD)
    post(Client(), REQUEST, email=EMAIL)
    assert post(Client(), RESET, key=key_from_the_email(), password=NEW_PASSWORD) == (401, [])
    assert post(Client(), LOGIN, email=EMAIL, password=NEW_PASSWORD) == (200, [])


def test_reset_link_works_once(manager: User) -> None:
    post(Client(), REQUEST, email=EMAIL)
    key = key_from_the_email()
    assert post(Client(), RESET, key=key, password=NEW_PASSWORD) == (401, [])

    # A link left in an email can't set a password again: the key is made from the password it replaces.
    assert post(Client(), RESET, key=key, password="mtu-mwingine-kabisa-99") == (400, ["invalid_password_reset"])
    assert post(Client(), LOGIN, email=EMAIL, password=NEW_PASSWORD) == (200, [])


def test_reset_ends_old_sessions(manager: User) -> None:
    # A phone that was stolen while logged in is logged out by the new password: a session is tied to the password it
    # started with (Django's session check).
    stolen = Client()
    assert post(stolen, LOGIN, email=EMAIL, password=PASSWORD) == (200, [])
    assert stolen.get(SESSION).status_code == 200

    post(Client(), REQUEST, email=EMAIL)
    post(Client(), RESET, key=key_from_the_email(), password=NEW_PASSWORD)
    assert stolen.get(SESSION).status_code == 401


def test_new_password_must_pass_the_checks(manager: User) -> None:
    post(Client(), REQUEST, email=EMAIL)
    status, codes = post(Client(), RESET, key=key_from_the_email(), password="12345678")
    assert status == 400
    assert "password_entirely_numeric" in codes
    assert post(Client(), LOGIN, email=EMAIL, password=PASSWORD) == (200, [])


def test_reset_tells_nobody_who_has_an_account(manager: User) -> None:
    # The same answer for an email nobody here has, and no mail to it: anyone could otherwise make us send mail to a
    # stranger (ACCOUNT_EMAIL_UNKNOWN_ACCOUNTS).
    assert post(Client(), REQUEST, email="mgeni@example.com") == post(Client(), REQUEST, email=EMAIL)
    assert [email.to for email in mail.outbox] == [[EMAIL]]


def test_reset_request_needs_csrf(manager: User) -> None:
    # Without the token, another website could fill a person's inbox with reset links.
    client = Client(enforce_csrf_checks=True)
    assert client.post(REQUEST, {"email": EMAIL}, content_type=JSON).status_code == 403
    assert mail.outbox == []


def test_reset_lifts_the_wrong_password_count(manager: User) -> None:
    # They forgot it, so they typed it wrong, five times, by phone: the limit stops them. A new password from the link
    # must work at once, by phone or by email: not "wait 5 minutes". allauth's own clean-up looks only in its own table
    # of addresses, which we leave empty (apps/people/accounts.py).
    for _ in range(5):
        post(Client(), LOGIN, phone=PHONE, password="not-the-password")
    assert post(Client(), LOGIN, phone=PHONE, password=PASSWORD) == (400, ["too_many_login_attempts"])

    post(Client(), REQUEST, email=EMAIL)
    post(Client(), RESET, key=key_from_the_email(), password=NEW_PASSWORD)
    assert post(Client(), LOGIN, phone=PHONE, password=NEW_PASSWORD) == (200, [])
    assert post(Client(), LOGIN, email=EMAIL, password=NEW_PASSWORD) == (200, [])


def test_reset_keeps_no_copy_of_the_email(manager: User) -> None:
    # allauth has its own table of a person's emails, and both the login and the reset trust it. Our User holds the
    # email, so that table must stay empty: a copy there would outlive a change of email (the two tests below). Its
    # default reset key writes one the moment anyone asks for a link, with no login at all.
    post(Client(), REQUEST, email=EMAIL)
    assert post(Client(), RESET, key=key_from_the_email(), password=NEW_PASSWORD) == (401, [])
    assert post(Client(), LOGIN, email=EMAIL, password=NEW_PASSWORD) == (200, [])
    assert post(Client(), LOGIN, phone=PHONE, password=NEW_PASSWORD) == (200, [])
    assert not EmailAddress.objects.exists()


def test_old_email_opens_nothing_after_a_change(manager: User) -> None:
    # Someone took over the manager's mailbox, so the email on their record is changed. A link already in that mailbox,
    # a new link asked for, and a login by the old email must all fail. A request made before the change is what could
    # have kept the old address alive.
    post(Client(), REQUEST, email=EMAIL)
    link_in_the_stolen_mailbox = key_from_the_email()
    mail.outbox.clear()
    manager.email = NEW_EMAIL
    manager.save()

    assert post(Client(), REQUEST, email=EMAIL) == (200, [])
    assert mail.outbox == []
    assert post(Client(), RESET, key=link_in_the_stolen_mailbox, password=NEW_PASSWORD) == (
        400,
        ["invalid_password_reset"],
    )
    assert post(Client(), LOGIN, email=EMAIL, password=PASSWORD) == (400, ["email_password_mismatch"])
    assert post(Client(), LOGIN, email=NEW_EMAIL, password=PASSWORD) == (200, [])


def test_a_reused_email_opens_only_its_new_owner(manager: User) -> None:
    # The old address is later given to someone else, perhaps at another shop. Its mailbox must get a link for that
    # person alone, and the old owner's password must not log in with it.
    post(Client(), REQUEST, email=EMAIL)
    mail.outbox.clear()
    manager.email = NEW_EMAIL
    manager.save()
    newcomer = User.objects.create_user(full_name="Mgeni Mfano", email=EMAIL, password="ufunguo-wa-mgeni-2026")

    post(Client(), REQUEST, email=EMAIL)
    assert len(mail.outbox) == 1
    assert post(Client(), LOGIN, email=EMAIL, password=PASSWORD) == (400, ["email_password_mismatch"])

    post(Client(), RESET, key=key_from_the_email(), password=NEW_PASSWORD)
    newcomer.refresh_from_db()
    manager.refresh_from_db()
    assert newcomer.check_password(NEW_PASSWORD)
    assert manager.check_password(PASSWORD)


def test_reset_requests_are_slowed_down(manager: User, settings: Settings) -> None:
    # 3 an hour per email: enough for a person, too few to fill their inbox. allauth's default, 5 a minute, would let a
    # stranger who knows the address send them 7,200 emails a day. The count's hour is read from the setting: a test
    # can't wait it out.
    assert settings.ACCOUNT_RATE_LIMITS["reset_password"].endswith(",3/h/key")
    for _ in range(3):
        assert post(Client(), REQUEST, email=EMAIL) == (200, [])
    assert Client().post(REQUEST, {"email": EMAIL}, content_type=JSON).status_code == 429
    assert len(mail.outbox) == 3


def test_reset_link_ends_after_an_hour(manager: User) -> None:
    # A link left in a mailbox for days is a way in for whoever opens that mailbox later. Still good until then: what
    # stopped it is the time, not the key.
    post(Client(), REQUEST, email=EMAIL)
    key = key_from_the_email()
    just_past_the_hour = datetime.now() + timedelta(hours=1, seconds=5)
    with mock.patch.object(PasswordResetTokenGenerator, "_now", return_value=just_past_the_hour):
        assert post(Client(), RESET, key=key, password=NEW_PASSWORD) == (400, ["invalid_password_reset"])
    assert post(Client(), RESET, key=key, password=NEW_PASSWORD) == (401, [])
