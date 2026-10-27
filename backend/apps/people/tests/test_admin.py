"""apps/people/tests/test_admin.py — the Django admin page for people (apps/people/admin.py).

The admin is the creator's back room (`admin.<domain>` later): the superuser sees and fixes people there
before any office screen exists. These tests drive it like a browser would, through Django's test client,
logged in as a fake superuser (the `superuser` and `superuser_client` fixtures, in backend/conftest.py).
"""

import pytest
from django.contrib import admin
from django.test import Client, RequestFactory

from apps.people.models import User

pytestmark = pytest.mark.django_db

USERS = "/admin/people/user/"
# The password the `superuser` fixture is made with (backend/conftest.py). If the two ever differ, the
# login test below fails, so they can't drift apart unnoticed.
PASSWORD = "a-long-test-password"


def test_admin_login_ignores_email_case(client: Client, superuser: User) -> None:
    # Through the real login page: people type their email in any letter case, and emails are stored in
    # lower case, so the login looks the lower-case form up (UserManager.get_by_natural_key). The admin's
    # form calls the login name `username`, whatever field it really is.
    response = client.post("/admin/login/", {"username": "ADMIN@Example.com", "password": PASSWORD, "next": "/admin/"})

    # A wrong login shows the form again (200); a right one goes on to the admin.
    assert response.status_code == 302
    assert response["Location"] == "/admin/"


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
