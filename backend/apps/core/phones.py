"""apps/core/phones.py — the phone normaliser: every phone number is stored one way, in E.164 form.

It owns one rule (02 §1, 03 §5.9): a phone is stored as `+255712345678`, never as it was typed, so the
same phone typed two ways is one number and a unique phone means one person. Every app that stores a
phone (people, contacts) calls this function before saving.
"""

import phonenumbers
from django.core.exceptions import ValidationError


def normalise_phone(raw: str, region: str = "TZ") -> str:
    """Return `raw` in E.164 form (`+255712345678`), or raise ValidationError with code `phone.invalid`.

    `region` is the country assumed when a number is typed without its code (`0712…`); a number that
    names its country (`+254…`) keeps it. TZ is MPC's country; a shop elsewhere would pass its own.
    `00255…` is refused, not read as +255: Tanzania dials abroad with 000, not 00. Type `+255…` or `0…`.
    """
    try:
        number = phonenumbers.parse(raw, region)
    except phonenumbers.NumberParseException:
        # Letters or an empty string: not a number at all.
        raise ValidationError("Not a phone number.", code="phone.invalid") from None
    # Parsing only reads the digits; this checks them against the real numbering plan of that country
    # (length and prefixes), so a typo like 12345 is caught here, not on the day we try to call.
    if not phonenumbers.is_valid_number(number):
        raise ValidationError("Not a valid phone number.", code="phone.invalid")
    return phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)
