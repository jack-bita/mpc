"""apps/people/accounts.py — what django-allauth asks of our people: the password login of the owner and managers
(AUTH-3; 03 §5.9; ADR-0038).

allauth runs the login itself: the check of the password, the session it starts, logout, and the slowing down of
guessers. Wherever a project's people differ from its defaults, it asks an adapter, a class the project names in
ACCOUNT_ADAPTER (config/settings/base.py). This file owns ours.

- Nobody signs up. The owner adds people (PPL-2), and sets a first password face to face (AUTH-6).
"""

from allauth.account.adapter import DefaultAccountAdapter
from django.http import HttpRequest


# allauth ships no types, so mypy knows its base class only as `Any`, and strict mode refuses a class built on one: the
# library's missing types, not ours (pyproject.toml). Each method we write below keeps its own type hints.
class AccountAdapter(DefaultAccountAdapter):  # type: ignore[misc]
    def is_open_for_signup(self, request: HttpRequest) -> bool:
        # Closed to everyone: a stranger who found the address could otherwise make themselves a person here. allauth
        # answers a sign-up with 403 before it reads what was sent.
        return False
