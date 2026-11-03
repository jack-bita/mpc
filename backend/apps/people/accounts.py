"""apps/people/accounts.py — what django-allauth asks of our people: the password login of the owner and managers
(AUTH-3; 03 §5.9; ADR-0038).

allauth runs the login itself: the check of the password, the session it starts, logout, and the slowing down of
guessers. Wherever a project's people differ from its defaults, it asks an adapter, a class the project names in
ACCOUNT_ADAPTER (config/settings/base.py). This file owns ours.

- Nobody signs up. The owner adds people (PPL-2), and sets a first password face to face (AUTH-6).
- A person logs in by email or by phone. allauth keeps no phones of its own: it asks here for a person's phone, and
  for the person a phone belongs to, both read from our User, in the one stored form, `+255…` (apps/core/phones.py).
- No SMS is ever sent. The owner typed each phone, face to face, so every phone counts as confirmed, and allauth's
  own check by an SMS code is off (ACCOUNT_PHONE_VERIFICATION_ENABLED). The hooks that would send one, or change a
  person's phone, are allauth's own, which refuse loudly (NotImplementedError): nothing should ever reach them.
- Wrong passwords count per person, a phone included (see _get_login_attempts_cache_key).
"""

from typing import Any

from allauth.account.adapter import DefaultAccountAdapter
from django.core.exceptions import ValidationError
from django.http import HttpRequest

from apps.core.phones import normalise_phone
from apps.people.models import User


# allauth ships no types, so mypy knows its base class only as `Any`, and strict mode refuses a class built on one: the
# library's missing types, not ours (pyproject.toml). Each method we write below keeps its own type hints.
class AccountAdapter(DefaultAccountAdapter):  # type: ignore[misc]
    def is_open_for_signup(self, request: HttpRequest) -> bool:
        # Closed to everyone: a stranger who found the address could otherwise make themselves a person here. The
        # sign-up route isn't even mounted (apps/people/api/password_urls.py); this is the second lock, for any other
        # way in that a later allauth feature might open.
        return False

    def clean_phone(self, phone: str) -> str:
        # Every phone allauth reads, the login form's included, in the one form we store (+255…), or refused with
        # `phone.invalid`. allauth's own field has already refused a phone written without its country code: the app
        # sends +255… (UI-5).
        return normalise_phone(phone)

    def get_user_by_phone(self, phone: str) -> User | None:
        # The person this phone belongs to, or None. allauth then checks the password, and that the person is active.
        # A phone is unique (PPL-1), so there is at most one. A User is no shop's row: read without the shop guard
        # (ADR-0037), as every login must start before it knows a shop.
        try:
            stored = normalise_phone(phone)
        except ValidationError:
            return None
        return User.objects.filter(phone=stored).first()

    def get_phone(self, user: User) -> tuple[str, bool] | None:
        # A person's phone, and whether it is confirmed: always, since the owner typed it face to face (PPL-2). So
        # allauth never asks the person to confirm it by an SMS code.
        if not user.phone:
            return None
        return user.phone, True

    def _get_login_attempts_cache_key(self, request: HttpRequest, **credentials: Any) -> str:
        # allauth counts a person's wrong passwords, 5 in 5 minutes *(its default)*, under a key made of the site's
        # address and the login name: the email, or else the username. A phone is neither, so every phone login would
        # share one key, the address alone: five wrong passwords for anyone's phone would lock every phone user out.
        # The phone joins the key, in its stored form (clean_phone), so each person's count is their own. allauth
        # keeps only the key's hash, never the phone itself. A private method of allauth's, so a later allauth could
        # rename it, and this would stop working unseen: test_wrong_passwords_count_per_phone pins it.
        key: str = super()._get_login_attempts_cache_key(request, **credentials)
        phone = credentials.get("phone")
        if phone and not credentials.get("email") and not credentials.get("username"):
            return f"{key}phone:{phone}"
        return key
