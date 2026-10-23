"""apps/people/tests/test_users.py — the rules every person in the system follows (02 §5, ADR-0012).

One `User` is one human, across every shop. Workers are added with a name and maybe a phone, and log in
with a PIN on shop devices, so phone, email and password are all optional. Only the superuser, who opens
the Django admin, needs an email: it is the admin's login name.

These are the project's first tests that use the database. pytest-django builds a throwaway
`test_<DB_NAME>` database from the migrations, runs each test inside a transaction and rolls it back
afterwards, so no test sees another test's rows and the development database is never touched.
"""

from io import StringIO

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError

from apps.people.models import User

# Every test in this file may use the database.
pytestmark = pytest.mark.django_db

# Fake data only: the repo is public (03 §10).
PASSWORD = "a-long-test-password"


def test_phone_stored_as_plus255() -> None:
    user = User.objects.create_user(full_name="Juma Demo", phone="0712 345 678")

    # Read it back from the database, not from the object in memory: this is what was really stored.
    user.refresh_from_db()
    assert user.phone == "+255712345678"


def test_phone_unique() -> None:
    User.objects.create_user(full_name="Juma Demo", phone="0712 345 678")

    # The same number typed another way is the same number, so it is refused too. Comparing the
    # normalised form is what makes "unique" mean something.
    with pytest.raises(ValidationError) as refused:
        User.objects.create_user(full_name="Asha Demo", phone="+255 712 345 678")
    assert "phone" in refused.value.message_dict


def test_phone_typed_with_brackets_is_accepted() -> None:
    # 18 characters as typed, longer than the 16-character column: the field cleans it before Django
    # checks the length (apps/core/fields.py), so a number copied from a message isn't refused.
    user = User.objects.create_user(full_name="Juma Demo", phone="(+255) 712 345 678")

    user.refresh_from_db()
    assert user.phone == "+255712345678"


def test_phone_saved_directly_is_still_normalised() -> None:
    # Code that skips create_user (a quick `create()` in a service or a seed) still stores the one
    # shape, and a search in any shape finds the person: the field cleans on every save and lookup.
    User.objects.create(full_name="Juma Demo", phone="0712 345 678")

    assert User.objects.get(phone="0712-345-678").phone == "+255712345678"


def test_invalid_phone_refused_on_the_phone_field() -> None:
    with pytest.raises(ValidationError) as refused:
        User.objects.create_user(full_name="Juma Demo", phone="12345")

    # Under the field's name, so a form shows it next to the phone box, and as a code, not a sentence,
    # so the screens can say it in Swahili or English (ADR-0032).
    assert refused.value.error_dict["phone"][0].code == "phone.invalid"


def test_email_unique_ignoring_case() -> None:
    User.objects.create_user(full_name="Asha Demo", email="asha@example.com")

    # People type their email in any letter case; it reaches the same inbox, so it is the same email.
    with pytest.raises(ValidationError) as refused:
        User.objects.create_user(full_name="Asha Demo", email="ASHA@Example.COM")
    assert "email" in refused.value.message_dict


def test_user_without_password() -> None:
    # A worker who only uses a PIN on shop devices: a name and nothing else (PIN comes with PPL-2).
    user = User.objects.create_user(full_name="Neema Demo")

    user.refresh_from_db()
    assert user.email is None
    assert user.phone is None
    # The password column is never empty: it holds a locked value that no typed password can match,
    # not even an empty one, so nobody can log in to this account with a password.
    assert not user.has_usable_password()
    assert not user.check_password("")


def test_many_people_without_phone_or_email() -> None:
    # Phone and email are optional, and unique only when given: a missing one is stored as NULL, and
    # PostgreSQL never counts two NULLs as the same value. A blank form field ("") must become NULL too,
    # or the second worker without a phone would clash with the first.
    User.objects.create_user(full_name="Juma Demo")
    User.objects.create_user(full_name="Neema Demo", phone="", email="")

    assert User.objects.filter(phone__isnull=True, email__isnull=True).count() == 2


@pytest.mark.parametrize("email", [None, ""])
def test_superuser_needs_email(email: str | None) -> None:
    # The superuser logs in to the Django admin by email (ADR-0012), so one without an email could
    # never log in. Refuse it when it is made, not when someone first tries to log in.
    with pytest.raises(ValueError, match="email"):
        User.objects.create_superuser(full_name="Admin Demo", email=email, password=PASSWORD)


def test_createsuperuser_by_email(monkeypatch: pytest.MonkeyPatch) -> None:
    # How the very first person is made, in the terminal (ADR-0012). --noinput takes the password from
    # this environment variable instead of asking for it.
    monkeypatch.setenv("DJANGO_SUPERUSER_PASSWORD", PASSWORD)

    call_command(
        "createsuperuser",
        interactive=False,
        email="Admin@Example.com",
        full_name="Admin Demo",
        stdout=StringIO(),  # keep the command's "Superuser created" line out of the test output
    )

    admin = User.objects.get()
    assert admin.email == "admin@example.com"  # stored in lower case, like every email
    assert admin.is_superuser
    assert admin.is_staff  # the Django admin lets in only staff
    assert admin.check_password(PASSWORD)


@pytest.mark.parametrize(
    "fields",
    [
        # Not a phone at all: a real phone would be cleaned by its field on the way in.
        pytest.param({"phone": "12345"}, id="phone_e164"),
        pytest.param({"email": "Asha@Example.com"}, id="email_lower_case"),
        pytest.param({"email": ""}, id="email_not_blank"),
        pytest.param({"language": "fr"}, id="language_known"),
        pytest.param({"is_superuser": True}, id="superuser_has_email"),
    ],
)
def test_database_refuses_a_row_that_breaks_a_rule(fields: dict[str, object]) -> None:
    # The database is the last guard (03 §5.6): code that skips create_user and saves a User directly
    # still can't store a row that breaks one of the five rules in User.Meta. One run per rule.
    with pytest.raises(IntegrityError):
        User(full_name="Juma Demo", **fields).save()


def test_broken_rule_comes_back_as_a_code() -> None:
    # The way a form checks a person (full_clean): a rule that spans two fields comes back under
    # `__all__`, with its code, which the screens translate (ADR-0032).
    superuser = User(full_name="Admin Demo", is_superuser=True)
    superuser.set_unusable_password()

    with pytest.raises(ValidationError) as refused:
        superuser.full_clean()

    assert [error.code for error in refused.value.error_dict["__all__"]] == ["user.superuser_needs_email"]
