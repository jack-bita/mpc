"""apps/people/tests/test_password_hashing.py — a person's password is stored as Argon2, at the cost we chose, and an
older hash moves to it at the next login (AUTH-3; 03 §10; apps/people/hashers.py).

The other tests use a fast, weak hasher (config/settings/test.py), so nothing else here would notice if the real list
changed. These read the real list from the base settings, and log in through the real route.

Fake data only: the repo is public (03 §10).
"""

import pytest
from django.contrib.auth.hashers import Argon2PasswordHasher, PBKDF2PasswordHasher, make_password
from django.test import Client, override_settings

from apps.people.models import User
from config.settings.base import PASSWORD_HASHERS

pytestmark = pytest.mark.django_db

LOGIN = "/_allauth/browser/v1/auth/login"
EMAIL = "meneja@example.com"
PASSWORD = "mbegu-za-mahindi-2026"
# The start of a stored hash names its algorithm and its cost, which is how Django knows when one is out of date.
OUR_COST = "argon2$argon2id$v=19$m=19456,t=2,p=1$"


def logs_in() -> bool:
    answer = Client().post(LOGIN, {"email": EMAIL, "password": PASSWORD}, content_type="application/json")
    return answer.status_code == 200


@override_settings(PASSWORD_HASHERS=PASSWORD_HASHERS)
def test_a_new_password_is_stored_as_argon2_at_our_cost() -> None:
    # Argon2 needs a lot of memory for every guess, which is what makes a stolen database slow to attack.
    person = User.objects.create_user(full_name="Meneja Mfano", email=EMAIL, password=PASSWORD)
    assert person.password.startswith(OUR_COST)
    assert logs_in()


# Every password set before this card is PBKDF2 (Django's default), the demo's superuser's included: it must keep
# working, not lock its owner out. And a cost we change later reaches each person the same way.
@pytest.mark.parametrize(
    "older", [PBKDF2PasswordHasher, Argon2PasswordHasher], ids=["pbkdf2", "argon2_at_another_cost"]
)
@override_settings(PASSWORD_HASHERS=PASSWORD_HASHERS)
def test_an_older_hash_logs_in_and_moves_to_our_cost(older: type) -> None:
    person = User.objects.create_user(full_name="Meneja Mfano", email=EMAIL)
    person.password = make_password(PASSWORD, hasher=older())
    person.save(update_fields=["password"])
    assert not person.password.startswith(OUR_COST)

    assert logs_in()
    person.refresh_from_db()
    assert person.password.startswith(OUR_COST)
    assert logs_in()


@override_settings(PASSWORD_HASHERS=PASSWORD_HASHERS)
def test_a_wrong_password_moves_no_hash() -> None:
    # Only someone who proved the password may cause a new hash to be written.
    person = User.objects.create_user(full_name="Meneja Mfano", email=EMAIL)
    person.password = make_password(PASSWORD, hasher=PBKDF2PasswordHasher())
    person.save(update_fields=["password"])
    stored = person.password

    Client().post(LOGIN, {"email": EMAIL, "password": "not-the-password"}, content_type="application/json")
    person.refresh_from_db()
    assert person.password == stored
