"""apps/people/accounts.py — what django-allauth asks of our people: the password login of the owner and managers
(AUTH-3; 03 §5.9; ADR-0038).

allauth runs the login itself: the check of the password, the session it starts, logout, and the slowing down of
guessers. Wherever a project's people differ from its defaults, it asks an adapter, a class the project names in
ACCOUNT_ADAPTER (config/settings/base.py). This file owns ours.

- Nobody signs up. The owner adds people (PPL-2), and sets a first password face to face (AUTH-6).
- A person logs in by email or by phone. allauth keeps no phones of its own: it asks here for the person a phone belongs
  to, read from our User, in the one stored form, `+255…` (apps/core/phones.py).
- No SMS is ever sent. The owner typed each phone, face to face, so allauth's own check by an SMS code is off
  (ACCOUNT_PHONE_VERIFICATION_ENABLED). The hooks that would send one, read a person's phone for it, or change that
  phone are allauth's own, which refuse loudly (NotImplementedError): nothing on our routes reaches them.
- Guessers are slowed down: allauth counts wrong passwords, 10 a minute per caller and 5 in 5 minutes per person *(its
  defaults)*, in a cache table of their own (`default`, CACHES, config/settings/base.py). What it counts by comes from
  here, and names nobody: a fingerprint of the caller's network, and of the person's login name. Honest limit: a
  stranger who knows Baba's phone can keep him locked out, by typing five wrong passwords every five minutes. Every
  login limit has this cost; two-factor codes are *Later*.
- A person who has an email may reset their password by a link sent to it; anyone else asks the owner (ADR-0038). A new
  password lifts the person's count of wrong passwords (see set_password).
"""

from typing import Any

from allauth.account.adapter import DefaultAccountAdapter
from allauth.core import ratelimit
from django.http import HttpRequest
from django.utils.crypto import salted_hmac

from apps.core.phones import normalise_phone
from apps.people.api.throttles import caller_fingerprint
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
        # The phone comes in the form we store: allauth's field has passed it through clean_phone above. A phone is
        # unique (PPL-1), so there is at most one. A User is no shop's row: read without the shop guard (ADR-0037), as
        # every login must start before it knows a shop.
        return User.objects.filter(phone=phone).first()

    def set_password(self, user: User, password: str) -> None:
        # Someone who forgot their password has usually typed it wrong a few times: with a new one, they must not still
        # be told to wait. allauth lifts the count itself, but only for the emails in its own table of addresses, which
        # we leave empty, as our User holds the email (apps/people/models.py). So it is lifted here, for each name the
        # person logs in by. `clear` also lifts the caller's own count, as allauth means it to: it is safe, as the
        # reset itself is slowed down.
        super().set_password(user, password)
        for login in (user.email, user.phone):
            if login:
                key = self._get_login_attempts_cache_key(self.request, email=login)
                ratelimit.clear(self.request, action="login_failed", key=key)

    def get_client_ip(self, request: HttpRequest) -> str:
        # Who allauth's limits count this caller as, and all allauth uses this for here: the same fingerprint of their
        # network as the pairing limits keep (apps/people/api/throttles.py), read from what the proxy in front saw, so a
        # phone can't take a new IPv6 address for every guess, or write a false one in a header. allauth leaves a value
        # that is no address as it is, and writes it into the row's key: so the table holds no address (03 §5.10).
        return caller_fingerprint("login", request)

    def _get_login_attempts_cache_key(self, request: HttpRequest, **credentials: Any) -> str:
        # Who allauth counts wrong passwords against. Its own key is made of the email or the username: a phone is
        # neither, so every phone login would share one key, and five wrong passwords for anyone's phone would lock
        # every phone user out. Ours is the login name, whichever it is, in its stored form (clean_phone), so each
        # person's count is their own. A fingerprint made with the server's secret key: allauth writes only a plain hash
        # of this into the row's key, and a plain hash of a phone number can be worked back, by trying every number.
        # A private method of allauth's, so a later allauth could rename it, and this would stop working unseen:
        # test_wrong_passwords_count_per_phone pins it.
        login = credentials.get("phone") or credentials.get("email") or credentials.get("username") or ""
        return salted_hmac("login.person", login.lower(), algorithm="sha256").hexdigest()
