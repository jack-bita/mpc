"""apps/core/fields.py — model fields every app can use. For now one: PhoneField.

A phone is stored one way, in E.164 (`+255712345678`, apps/core/phones.py). PhoneField cleans what was
typed before Django checks its length, so `(+255) 712 345 678` is accepted. People use it now; contacts
will use it for customers' phones.
"""

from typing import Any

from django import forms
from django.core.exceptions import ValidationError
from django.db import models

from apps.core.phones import normalise_phone


class PhoneField(models.CharField[str | None, str | None]):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        # E.164 is a + and at most 15 digits, so the column never needs more than 16 characters.
        kwargs.setdefault("max_length", 16)
        super().__init__(*args, **kwargs)

    def to_python(self, value: Any) -> Any:
        # Django runs this first when it checks a value (full_clean, and so the admin's forms too), before
        # the length check: "(+255) 712 345 678" is 18 characters typed but 13 stored. A bad number fails
        # here with code `phone.invalid`, under this field's name.
        value = super().to_python(value)
        if not value:
            return value
        return normalise_phone(value)

    def get_prep_value(self, value: Any) -> Any:
        # Django also runs to_python here (CharField does), on every save and every lookup, so a phone
        # saved or searched in any shape becomes the stored shape. A value that isn't a phone at all goes
        # on as it is: a lookup then finds nothing, and a save is refused by the database rule.
        try:
            return super().get_prep_value(value)
        except ValidationError:
            return value

    def formfield(self, **kwargs: Any) -> forms.Field | None:
        # A form's box takes what people type, which is longer than what is stored: spaces, dashes,
        # brackets. 32 is plenty; the column stays 16.
        return super().formfield(**{"max_length": 32, **kwargs})
