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
from django.views.debug import ExceptionReporter

from apps.core.models import ChangeOp
from apps.core.permissions import RoleTemplate
from apps.core.tenancy import shop_context
from apps.people.admin import ChooseOwnPasswordForm
from apps.people.models import StaffMember, User
from apps.people.services import add_staff
from apps.shops.models import Shop, Side
from tests.change_log import lines_written

pytestmark = pytest.mark.django_db

USERS = "/admin/people/user/"
LOGIN = "/_allauth/browser/v1/auth/login"
# The password the `superuser` fixture is made with (backend/conftest.py). If the two ever differ, the
# login test below fails, so they can't drift apart unnoticed.
PASSWORD = "a-long-test-password"
NEW_PASSWORD = "mbolea-ya-kupandia-2027"
PHONE = "+255712345678"
TEST_CLIENT_FILES = ("django/test/client.py", "test_admin.py")


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


def test_admin_first_password_on_the_persons_page_sets_the_mark(superuser_client: Client) -> None:
    # A person added with no password, given one later on their own page. Django shows no "Disabled" switch there, as
    # there is no password to disable yet, so the form sends less than a reset's: this pins that the mark still goes on.
    juma = User.objects.create_user(full_name="Juma Demo", phone=PHONE)
    assert not juma.has_usable_password()
    sent = {"password1": NEW_PASSWORD, "password2": NEW_PASSWORD}
    assert superuser_client.post(f"{USERS}{juma.pk}/password/", sent).status_code == 302
    juma.refresh_from_db()
    assert juma.check_password(NEW_PASSWORD)
    assert juma.must_change_password is True


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


def test_admin_takes_the_spaces_off_a_password(superuser_client: Client) -> None:
    # Django's admin forms keep spaces around a password, and allauth's login takes them off what is typed, so one
    # stored with them could never log in. Tried through the real login.
    baba = User.objects.create_user(full_name="Baba Mfano", phone=PHONE, password=PASSWORD)
    reset_in_the_admin(superuser_client, baba, f" {NEW_PASSWORD} ")
    login = {"phone": PHONE, "password": NEW_PASSWORD}
    assert Client().post(LOGIN, login, content_type="application/json").status_code == 200


def test_admin_first_password_loses_its_spaces_too(superuser_client: Client) -> None:
    sent = {
        "full_name": "Baba Mfano",
        "phone": PHONE,
        "email": "",
        "language": "sw",
        "usable_password": "true",
        "password1": f"{NEW_PASSWORD} ",
        "password2": f"{NEW_PASSWORD} ",
    }
    assert superuser_client.post(f"{USERS}add/", sent).status_code == 302
    login = {"phone": PHONE, "password": NEW_PASSWORD}
    assert Client().post(LOGIN, login, content_type="application/json").status_code == 200


def test_admin_refuses_a_password_of_only_spaces(superuser_client: Client) -> None:
    # Nothing is left of it once the spaces are off. 200: the form again, with its error, and nothing saved.
    baba = User.objects.create_user(full_name="Baba Mfano", phone=PHONE, password=PASSWORD)
    sent = {"password1": " " * 12, "password2": " " * 12, "usable_password": "true"}
    assert superuser_client.post(f"{USERS}{baba.pk}/password/", sent).status_code == 200
    baba.refresh_from_db()
    assert baba.check_password(PASSWORD)
    assert baba.must_change_password is False


def change_own_password(client: Client, new: str, *, old: str = PASSWORD) -> int:
    # Django's own page where someone who can open the admin changes their own password.
    sent = {"old_password": old, "new_password1": new, "new_password2": new}
    return client.post("/admin/password_change/", sent).status_code


def test_own_password_page_clears_the_mark(superuser_client: Client, superuser: User) -> None:
    # Someone who can open the admin chooses their own here too. Django's own form said it worked, and left the mark.
    User.objects.filter(pk=superuser.pk).update(must_change_password=True)
    assert change_own_password(superuser_client, NEW_PASSWORD) == 302
    superuser.refresh_from_db()
    assert superuser.check_password(NEW_PASSWORD)
    assert superuser.must_change_password is False


def test_own_password_page_refuses_the_temporary_one(superuser_client: Client, superuser: User) -> None:
    # The same rule as the change route: someone else typed that one. 200: the form again, with its error.
    User.objects.filter(pk=superuser.pk).update(must_change_password=True)
    assert change_own_password(superuser_client, PASSWORD) == 200
    superuser.refresh_from_db()
    assert superuser.must_change_password is True


def test_own_password_page_takes_the_spaces_off(superuser_client: Client) -> None:
    # As the admin's other forms: allauth's login takes them off what is typed, so one stored with them never logs in.
    assert change_own_password(superuser_client, f" {NEW_PASSWORD} ") == 302
    login = {"email": "admin@example.com", "password": NEW_PASSWORD}
    assert Client().post(LOGIN, login, content_type="application/json").status_code == 200


@pytest.mark.parametrize(
    ("first", "second"),
    [(" " * 12, " " * 12), (" " * 12, NEW_PASSWORD), ("123", "   ")],
)
def test_own_password_page_refuses_what_leaves_nothing(
    superuser_client: Client, superuser: User, first: str, second: str
) -> None:
    # Spaces alone are no password. Taken off too late, after the form's own "required" check, they stored the hash of
    # nothing: the old password dead, the page saying it worked, and no login that takes an empty password. Or they let
    # "123" past the checker, which skips an empty box. 200: the form again, and nothing changed.
    sent = {"old_password": PASSWORD, "new_password1": first, "new_password2": second}
    assert superuser_client.post("/admin/password_change/", sent).status_code == 200
    superuser.refresh_from_db()
    assert superuser.check_password(PASSWORD)


def test_own_password_page_leaves_the_rest_of_the_row_alone(superuser: User) -> None:
    # The visit read the person's row when it began, and someone takes the admin away from them a moment later. Django's
    # own form saves the whole row, which would give it back with what it read.
    read_by_the_visit = User.objects.get(pk=superuser.pk)
    User.objects.filter(pk=superuser.pk).update(is_staff=False)

    sent = {"old_password": PASSWORD, "new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD}
    form = ChooseOwnPasswordForm(read_by_the_visit, data=sent)
    assert form.is_valid()
    form.save()

    stored = User.objects.get(pk=superuser.pk)
    assert stored.is_staff is False
    assert stored.check_password(NEW_PASSWORD)


def test_own_password_page_lifts_the_wrong_password_count(superuser_client: Client) -> None:
    wrong = {"email": "admin@example.com", "password": "not-the-password"}
    for _ in range(5):
        Client().post(LOGIN, wrong, content_type="application/json")
    assert change_own_password(superuser_client, NEW_PASSWORD) == 302
    login = {"email": "admin@example.com", "password": NEW_PASSWORD}
    assert Client().post(LOGIN, login, content_type="application/json").status_code == 200


@pytest.mark.parametrize(
    ("page", "sent"),
    [
        ("reset", {"password1": NEW_PASSWORD, "password2": NEW_PASSWORD, "usable_password": "true"}),
        ("own", {"old_password": PASSWORD, "new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD}),
    ],
)
def test_admin_keeps_a_password_out_of_error_reports(
    superuser_client: Client, superuser: User, page: str, sent: dict[str, str]
) -> None:
    # The hash can run out of memory, and the library underneath names the password `secret`. Hidden from the forms'
    # save down (PasswordTypedHereIsTemporary, ChooseOwnPasswordForm).
    address = f"{USERS}{superuser.pk}/password/" if page == "reset" else "/admin/password_change/"
    crashing = mock.patch("django.contrib.auth.base_user.make_password", side_effect=MemoryError("out of memory"))
    with crashing, pytest.raises(MemoryError) as crash:
        superuser_client.post(address, sent)
    assert_nothing_shows(crash, NEW_PASSWORD)


def assert_nothing_shows(crash: pytest.ExceptionInfo[BaseException], *secrets: str) -> None:
    # What Django's error report would show of a crash, read as a server would write it.
    frames = ExceptionReporter(None, crash.type, crash.value, crash.tb).get_traceback_frames()
    # Only the server's frames: the test client's own hold what this test sent.
    on_the_server = [frame for frame in frames if not frame["filename"].endswith(TEST_CLIENT_FILES)]
    shown = [str(value) for frame in on_the_server for _, value in frame["vars"]]
    assert shown
    assert not [value for value in shown for secret in secrets if secret in value]


def test_own_password_page_keeps_the_old_password_out_of_error_reports(superuser_client: Client) -> None:
    # For someone with the mark on, the old password is the temporary one. It is checked by clean_old_password, outside
    # the form's clean and save, and Django's own version hides only the name `old_password`, so the frames below it
    # show the same password as `raw_password`.
    sent = {"old_password": PASSWORD, "new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD}
    crashing = mock.patch("django.contrib.auth.base_user.check_password", side_effect=MemoryError("out of memory"))
    with crashing, pytest.raises(MemoryError) as crash:
        superuser_client.post("/admin/password_change/", sent)
    assert_nothing_shows(crash, PASSWORD, NEW_PASSWORD)


def test_own_password_page_keeps_the_new_password_out_of_error_reports(
    superuser_client: Client, superuser: User
) -> None:
    # With the mark on, clean hashes the new password too, to compare it with the temporary one. The first check, of the
    # old password, passes; the second crashes.
    User.objects.filter(pk=superuser.pk).update(must_change_password=True)
    sent = {"old_password": PASSWORD, "new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD}
    crashing = mock.patch(
        "django.contrib.auth.base_user.check_password", side_effect=[True, MemoryError("out of memory")]
    )
    with crashing, pytest.raises(MemoryError) as crash:
        superuser_client.post("/admin/password_change/", sent)
    assert_nothing_shows(crash, PASSWORD, NEW_PASSWORD)


def test_reset_page_keeps_the_password_out_of_error_reports_in_its_checks(
    superuser_client: Client, superuser: User
) -> None:
    # A crash while the form looks the password over, before anything is saved.
    sent = {"password1": NEW_PASSWORD, "password2": NEW_PASSWORD, "usable_password": "true"}
    crashing = mock.patch("apps.people.admin._take_off_spaces", side_effect=MemoryError("out of memory"))
    with crashing, pytest.raises(MemoryError) as crash:
        superuser_client.post(f"{USERS}{superuser.pk}/password/", sent)
    assert_nothing_shows(crash, NEW_PASSWORD)


def test_own_password_page_still_refuses_a_wrong_old_password(superuser_client: Client, superuser: User) -> None:
    # Its check is written out here now, to hide its variables, so its one job is pinned too.
    assert change_own_password(superuser_client, NEW_PASSWORD, old="not-the-password") == 200
    superuser.refresh_from_db()
    assert superuser.check_password(PASSWORD)


def test_admin_shows_the_mark_read_only(superuser_client: Client) -> None:
    # The superuser sees whether a person has chosen their own yet, and can't tick it off for them: that would leave a
    # password someone else knows, with nothing to show for it.
    juma = User.objects.create_user(full_name="Juma Demo")
    response = superuser_client.get(f"{USERS}{juma.pk}/change/")
    assert "must_change_password" in response.context["adminform"].readonly_fields
    assert "must_change_password" not in response.context["adminform"].form.fields


def test_admin_shows_the_font_read_only(superuser_client: Client) -> None:
    # Only the person changes their font (03 §7.4, ADR-0039): the superuser can see which one Asha reads, to help her on
    # the phone, but has no box to change it for her. Nor is it asked for when a person is added: everyone starts on
    # the default one.
    asha = User.objects.create_user(full_name="Asha Demo")
    response = superuser_client.get(f"{USERS}{asha.pk}/change/")
    assert "font" in response.context["adminform"].readonly_fields
    assert "font" not in response.context["adminform"].form.fields

    added = superuser_client.get(f"{USERS}add/")
    assert "font" not in added.context["adminform"].form.fields


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


def test_switching_a_person_off_in_the_admin_reaches_their_shops(
    superuser_client: Client, staff_a: StaffMember
) -> None:
    # The superuser opens Juma's page and clears "Active": the admin's own save goes through change_person, so each
    # shop's laptops drop him (SYNC-15). The form sends every field it shows; a box left clear is not sent at all.
    juma = User.objects.get(pk=staff_a.user_id)
    edited = {"full_name": juma.full_name, "phone": "", "email": "", "language": juma.language}
    with lines_written(staff_a.shop_id) as lines:
        response = superuser_client.post(f"{USERS}{juma.pk}/change/", edited)

    assert response.status_code == 302, response.content
    assert User.objects.get(pk=juma.pk).is_active is False
    assert lines == [("staff", staff_a.pk, ChangeOp.ARCHIVE)]
