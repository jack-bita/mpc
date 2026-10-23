"""apps/people/tests/test_admin.py — the Django admin page for people (apps/people/admin.py).

The admin is the creator's back room (`admin.<domain>` later): the superuser sees and fixes people there
before any office screen exists. These tests drive it like a browser would, through Django's test client,
logged in as a fake superuser.
"""

import pytest
from django.test import Client

from apps.people.models import User

pytestmark = pytest.mark.django_db

USERS = "/admin/people/user/"


@pytest.fixture
def superuser_client(client: Client) -> Client:
    # Our own fixture, not pytest-django's `admin_client`: that one calls create_superuser without a
    # full name, which our User requires.
    superuser = User.objects.create_superuser(
        full_name="Admin Demo", email="admin@example.com", password="a-long-test-password"
    )
    client.force_login(superuser)
    return client


def test_admin_adds_a_worker_with_phone_only(superuser_client: Client) -> None:
    # What the owner will do most: a worker with a name and a phone, no email and no password (02 §5).
    response = superuser_client.post(
        f"{USERS}add/",
        {
            "full_name": "Juma Demo",
            "phone": "0712 345 678",
            "email": "",
            "language": "sw",
            "usable_password": "false",  # Django's switch for "no password-based login"
        },
    )

    assert response.status_code == 302  # saved, and sent on to the next page
    juma = User.objects.get(full_name="Juma Demo")
    assert juma.phone == "+255712345678"  # the admin goes through the same clean() as create_user
    assert juma.email is None
    assert not juma.has_usable_password()


def test_admin_shows_id_read_only(superuser_client: Client) -> None:
    juma = User.objects.create_user(full_name="Juma Demo")

    response = superuser_client.get(f"{USERS}{juma.pk}/change/")

    # Shown, so the superuser can match a person with a log line or a device's record...
    assert str(juma.pk) in response.content.decode()
    # ...but there is no box to type a new one into. The id stays editable in the model on purpose, so
    # DRF keeps the id a device sends (ADR-0007, CORE-1); a changed id in the admin would save a copy
    # of the person instead of changing them.
    assert "id" not in response.context["adminform"].form.fields


def test_admin_cannot_delete_a_user(superuser_client: Client) -> None:
    juma = User.objects.create_user(full_name="Juma Demo")

    # "post": "yes" is the admin's "Yes, I'm sure" button on the delete page.
    response = superuser_client.post(f"{USERS}{juma.pk}/delete/", {"post": "yes"})

    # Nothing is deleted: a person who must not log in is switched off (`is_active`), and their name
    # stays on everything they did.
    assert response.status_code == 403
    assert User.objects.filter(pk=juma.pk).exists()
