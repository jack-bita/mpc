"""apps/people/tests/test_admin.py — the Django admin page for people (apps/people/admin.py).

The admin is the creator's back room (`admin.<domain>` later): the superuser sees and fixes people there
before any office screen exists. These tests drive it like a browser would, through Django's test client,
logged in as a fake superuser (the `superuser` and `superuser_client` fixtures, in backend/conftest.py).
"""

from collections.abc import Callable
from unittest import mock

import pytest
from allauth.account.models import EmailAddress
from django.contrib import admin
from django.contrib.auth.hashers import MD5PasswordHasher
from django.test import Client, RequestFactory

from apps.core.permissions import RoleTemplate
from apps.core.tenancy import shop_context
from apps.people.models import StaffMember, User
from apps.people.services import add_staff
from apps.shops.models import Shop, Side

pytestmark = pytest.mark.django_db

USERS = "/admin/people/user/"
LOGIN = "/_allauth/browser/v1/auth/login"
# The password the `superuser` fixture is made with (backend/conftest.py). If the two ever differ, the
# login test below fails, so they can't drift apart unnoticed.
PASSWORD = "a-long-test-password"
NEW_PASSWORD = "mbolea-ya-kupandia-2027"
PHONE = "+255712345678"


def test_admin_login_ignores_email_case(client: Client, superuser: User) -> None:
    # Through the real login page: people type their email in any letter case, and emails are stored in
    # lower case, so the login looks the lower-case form up (allauth's check, AUTHENTICATION_BACKENDS). The
    # admin's form calls the login name `username`, whatever field it really is.
    response = client.post("/admin/login/", {"username": "ADMIN@Example.com", "password": PASSWORD, "next": "/admin/"})

    # A wrong login shows the form again (200); a right one goes on to the admin.
    assert response.status_code == 302
    assert response["Location"] == "/admin/"


def test_allauth_table_of_addresses_is_not_in_the_admin(superuser_client: Client) -> None:
    # allauth's login and reset trust that table, so a row typed there would be a login name for a person, set past the
    # phone cleaner and the audit trail (PPL-2). Our User holds the email, and the table stays empty.
    assert not admin.site.is_registered(EmailAddress)
    assert superuser_client.get("/admin/account/emailaddress/").status_code == 404


def hashes_at_the_admin_door(email: str, password: str) -> int:
    # How many times one login attempt hashes the password. Every hash passes through the hasher's `encode`, its
    # check included, and the test settings' hasher is MD5 (config/settings/test.py).
    with mock.patch.object(MD5PasswordHasher, "encode", autospec=True, side_effect=MD5PasswordHasher.encode) as hashing:
        Client().post("/admin/login/", {"username": email, "password": password})
    return hashing.call_count


def test_admin_login_takes_one_hash_whatever_is_typed() -> None:
    # The hash is the slow part of a login, so its count shows in how long the answer takes. The admin's login has no
    # limit yet (04, DATA-1), and a manager who isn't staff sees the same page for a right password and a wrong one.
    # Two checkers would hash a wrong password twice and a right one once: a stranger could time guesses here, spot the
    # right password, then use it once at the real login, past every limit.
    User.objects.create_user(full_name="Meneja Mfano", email="meneja@example.com", password=PASSWORD)
    assert hashes_at_the_admin_door("meneja@example.com", PASSWORD) == 1
    assert hashes_at_the_admin_door("meneja@example.com", "not-the-password") == 1
    assert hashes_at_the_admin_door("mgeni@example.com", PASSWORD) == 1


@pytest.mark.parametrize(
    "typed",
    [
        "0712 345 678",
        "(+255) 712 345 678",  # longer than the column: the form's box must still take it
    ],
)
def test_admin_adds_a_worker_with_phone_only(superuser_client: Client, typed: str) -> None:
    # What the owner will do most: a worker with a name and a phone, no email and no password (02 §5).
    response = superuser_client.post(
        f"{USERS}add/",
        {
            "full_name": "Juma Demo",
            "phone": typed,
            "email": "",
            "language": "sw",
            "usable_password": "false",  # Django's switch for "no password-based login"
        },
    )

    assert response.status_code == 302  # saved, and sent on to the next page
    juma = User.objects.get(full_name="Juma Demo")
    assert juma.phone == "+255712345678"  # cleaned by the same field and rules as in create_user
    assert juma.email is None
    assert not juma.has_usable_password()


def reset_in_the_admin(client: Client, person: User, password: str = NEW_PASSWORD) -> None:
    # The admin's page for a person's password, as the superuser fills it in.
    sent = {"password1": password, "password2": password, "usable_password": "true"}
    response = client.post(f"{USERS}{person.pk}/password/", sent)
    assert response.status_code == 302  # saved, and sent on to the next page


def test_superuser_resets_the_owners_password(
    superuser_client: Client, shop_a: Shop, give_role: Callable[[StaffMember, RoleTemplate, Side | None], None]
) -> None:
    # Nobody at the shop may reset the owner's (set_temporary_password), so he comes to the superuser, who types one and
    # tells him. He logs in with it, and must choose his own, so the superuser doesn't go on knowing it (ADR-0038).
    baba = User.objects.create_user(full_name="Baba Mfano", phone=PHONE, password=PASSWORD)
    with shop_context(shop_a):
        staff = add_staff(shop=shop_a, user=baba, display_name="Baba", by=None)
    give_role(staff, RoleTemplate.OWNER, None)

    reset_in_the_admin(superuser_client, baba)

    phone = Client()
    login = {"phone": PHONE, "password": NEW_PASSWORD}
    assert phone.post(LOGIN, login, content_type="application/json").status_code == 200
    answer = phone.get("/api/v1/shops/sides/")
    assert (answer.status_code, answer.json()["code"]) == (403, "password.must_change")


def test_admin_reset_sets_the_mark(superuser_client: Client) -> None:
    juma = User.objects.create_user(full_name="Juma Demo", phone=PHONE, password=PASSWORD)
    reset_in_the_admin(superuser_client, juma)
    juma.refresh_from_db()
    assert juma.check_password(NEW_PASSWORD)
    assert juma.must_change_password is True


def test_admin_first_password_sets_the_mark(superuser_client: Client) -> None:
    # "First or forgotten" (ADR-0038): a new owner's first password is typed here too, until PPL-4's screen, and it is
    # no more their own than a reset one.
    response = superuser_client.post(
        f"{USERS}add/",
        {
            "full_name": "Baba Mfano",
            "phone": PHONE,
            "email": "",
            "language": "sw",
            "usable_password": "true",
            "password1": NEW_PASSWORD,
            "password2": NEW_PASSWORD,
        },
    )
    assert response.status_code == 302
    baba = User.objects.get(full_name="Baba Mfano")
    assert baba.check_password(NEW_PASSWORD)
    assert baba.must_change_password is True


def test_admin_adding_with_no_password_sets_no_mark(superuser_client: Client) -> None:
    # A PIN-only worker has no password to change, and the mark would say otherwise.
    sent = {"full_name": "Juma Demo", "phone": PHONE, "email": "", "language": "sw", "usable_password": "false"}
    assert superuser_client.post(f"{USERS}add/", sent).status_code == 302
    assert User.objects.get(full_name="Juma Demo").must_change_password is False


def test_admin_disabling_a_password_clears_the_mark(superuser_client: Client) -> None:
    # No password at all now, so nothing left to replace. "unset-password" is the name of Django's own button.
    juma = User.objects.create_user(full_name="Juma Demo", phone=PHONE, password=PASSWORD)
    User.objects.filter(pk=juma.pk).update(must_change_password=True)
    sent = {"usable_password": "false", "unset-password": "1"}
    assert superuser_client.post(f"{USERS}{juma.pk}/password/", sent).status_code == 302
    juma.refresh_from_db()
    assert not juma.has_usable_password()
    assert juma.must_change_password is False


def test_admin_reset_lifts_the_wrong_password_count(superuser_client: Client) -> None:
    # He came to the superuser because he kept typing it wrong: the limit stops him, and the new one must work at once.
    baba = User.objects.create_user(full_name="Baba Mfano", phone=PHONE, password=PASSWORD)
    wrong = {"phone": PHONE, "password": "not-the-password"}
    for _ in range(5):
        Client().post(LOGIN, wrong, content_type="application/json")
    right = {"phone": PHONE, "password": PASSWORD}
    assert Client().post(LOGIN, right, content_type="application/json").status_code == 400

    reset_in_the_admin(superuser_client, baba)

    new = {"phone": PHONE, "password": NEW_PASSWORD}
    assert Client().post(LOGIN, new, content_type="application/json").status_code == 200


def test_admin_shows_the_mark_read_only(superuser_client: Client) -> None:
    # The superuser sees whether a person has chosen their own yet, and can't tick it off for them: that would leave a
    # password someone else knows, with nothing to show for it.
    juma = User.objects.create_user(full_name="Juma Demo")
    response = superuser_client.get(f"{USERS}{juma.pk}/change/")
    assert "must_change_password" in response.context["adminform"].readonly_fields
    assert "must_change_password" not in response.context["adminform"].form.fields


def test_admin_shows_id_read_only(superuser_client: Client) -> None:
    juma = User.objects.create_user(full_name="Juma Demo")

    response = superuser_client.get(f"{USERS}{juma.pk}/change/")

    # Shown, so the superuser can match a person with a log line or a device's record... (Asked of the
    # admin directly: the id is in the page anyway, in the History link, so searching the page proves nothing.)
    assert "id" in response.context["adminform"].readonly_fields
    # ...but there is no box to type a new one into. The id stays editable in the model on purpose, so
    # DRF keeps the id a device sends (ADR-0007, CORE-1); a changed id in the admin would save a copy
    # of the person instead of changing them.
    assert "id" not in response.context["adminform"].form.fields


def test_admin_cannot_delete_a_user(superuser_client: Client, superuser: User) -> None:
    juma = User.objects.create_user(full_name="Juma Demo")

    # "post": "yes" is the admin's "Yes, I'm sure" button on the delete page.
    response = superuser_client.post(f"{USERS}{juma.pk}/delete/", {"post": "yes"})

    # Nothing is deleted: a person who must not log in is switched off (`is_active`), and their name
    # stays on everything they did.
    assert response.status_code == 403
    assert User.objects.filter(pk=juma.pk).exists()

    # Nor many at once: the list page's "Delete selected" action is gone too.
    request = RequestFactory().get(USERS)
    request.user = superuser
    assert "delete_selected" not in admin.site.get_model_admin(User).get_actions(request)
