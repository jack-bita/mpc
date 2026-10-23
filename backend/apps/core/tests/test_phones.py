"""apps/core/tests/test_phones.py — tests for the phone normaliser in apps/core/phones.py.

Every phone is stored one way, in international form (E.164: `+`, the country code, the number without
its leading 0), so the same phone typed two ways is one number and "unique" means something (03 §5.9).
No @pytest.mark.django_db: pytest-django blocks the database here, which also proves the normaliser is
a pure function that never queries it.
"""

import pytest
from django.core.exceptions import ValidationError

from apps.core.phones import normalise_phone


@pytest.mark.parametrize(
    "typed",
    [
        "0712 345 678",  # how most people write it
        "0712345678",
        "255712345678",  # the country code without the +
        "+255 712-345-678",
        "  0712 345 678  ",  # spaces copied in from a message
    ],
)
def test_tanzanian_number_typed_any_way_is_one_number(typed: str) -> None:
    assert normalise_phone(typed) == "+255712345678"


def test_foreign_number_keeps_its_country() -> None:
    # TZ is only the default, for numbers typed without a country code. A number that names its country
    # keeps it: a Kenyan supplier's phone must not become a Tanzanian one.
    assert normalise_phone("+254 712 345 678") == "+254712345678"


@pytest.mark.parametrize(
    "typed",
    [
        "12345",  # too short to be anyone's phone
        "07123456789",  # one digit too many
        "abc",
        "",
    ],
)
def test_nonsense_is_refused(typed: str) -> None:
    with pytest.raises(ValidationError) as refused:
        normalise_phone(typed)

    # A code, not a sentence: the screens show it in Swahili or English (ADR-0032).
    assert refused.value.code == "phone.invalid"
