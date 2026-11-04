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
  phone are allauth's own, which do nothing or refuse loudly (NotImplementedError): nothing on our routes reaches them.
- Guessers are slowed down: allauth counts wrong passwords, 10 a minute per caller and 5 in 5 minutes per login name
  *(its defaults)*, in a cache table of their own (`default`, CACHES, config/settings/base.py). A person with an email
  and a phone has a count for each. What it counts by comes from here, and names nobody: a fingerprint of the caller's
  network, and of the login name. Honest limit: a stranger who knows Baba's phone can keep him locked out, by typing
  five wrong passwords every five minutes. Every login limit has this cost; two-factor codes are *Later*.
- A person who has an email may reset their password by a link sent to it; anyone else asks the owner (ADR-0038). A new
  password lifts the person's count of wrong passwords (see set_password).
- A person who chooses a password, by the change route or by a link, has their "must change password" mark taken off,
  and may not choose the temporary one they were given: the owner knows it (AUTH-6; see clean_password, set_password).
"""

from typing import Any

from allauth.account.adapter import DefaultAccountAdapter
from allauth.account.auth_backends import AuthenticationBackend
from allauth.core import ratelimit
from django.core.exceptions import ValidationError
from django.http import HttpRequest
from django.views.decorators.debug import sensitive_variables

from apps.core.phones import normalise_phone
from apps.people.api.throttles import caller_fingerprint
from apps.people.login_counts import login_count_key
from apps.people.models import User


# allauth ships no types, so mypy knows these base classes only as `Any`, and strict mode refuses a class built on one:
# the library's missing types, not ours (pyproject.toml). Each method we write below keeps its own type hints.
class PasswordBackend(AuthenticationBackend):  # type: ignore[misc]
    # allauth's checker, for every login, the admin's too (AUTHENTICATION_BACKENDS, config/settings/base.py), with every
    # variable from here down hidden from Django's error reports. A route's own hiding doesn't reach here: Django's
    # authenticate() hides only `credentials`, by name, and the nearest rule wins, so the frames below it would show the
    # password as `password`, and at the bottom of the hash as `secret`. Running out of memory there is the likeliest
    # crash on the demo's 512 MB, and the password could be a temporary one (03 §5.9).
    @sensitive_variables()
    def authenticate(self, request: HttpRequest | None, **credentials: Any) -> User | None:
        user: User | None = super().authenticate(request, **credentials)
        return user


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

    def clean_password(self, password: str, user: User | None = None) -> str:
        # Every password a person chooses passes here, by the change route or by a link. While the mark is on, the
        # current one is the one the owner typed (ADR-0038): choosing it again would leave the owner knowing it for
        # good, with the mark off and nothing to show for it. An error code of our own, which UI-5's form translates
        # (ADR-0032).
        if user is not None and user.must_change_password and user.check_password(password):
            raise ValidationError("Choose a password other than the temporary one.", code="password.same_as_temporary")
        cleaned: str = super().clean_password(password, user)
        return cleaned

    def set_password(self, user: User, password: str) -> None:
        # Only a person choosing their own comes here: the change route and the reset link. A temporary password is set
        # by our own service, past this method (set_temporary_password, apps/people/services.py). So the mark comes off
        # here, in one save with the new password: never one without the other.
        user.set_password(password)
        user.must_change_password = False
        # These two columns alone, not allauth's own save of the whole row: this copy was read when the visit began, so
        # saving all of it could undo what happened since, such as the superuser switching this person off.
        user.save(update_fields=["password", "must_change_password"])
        # Someone who forgot their password has usually typed it wrong a few times: with a new one, they must not still
        # be told to wait. allauth lifts the count itself, but only for the emails in its own table of addresses, which
        # stays empty, as our User holds the email (ACCOUNT_PASSWORD_RESET_TOKEN_GENERATOR, config/settings/base.py). So
        # it is lifted here, for each name the person logs in by. `clear` also lifts the caller's own count, as allauth
        # means it to: it is safe, as the reset itself is slowed down.
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
        # every phone user out. Ours is the login name, whichever it is (apps/people/login_counts.py).
        # A private method of allauth's, so a later allauth could rename it, and this would stop working unseen:
        # test_wrong_passwords_count_per_phone pins it.
        login = credentials.get("phone") or credentials.get("email") or credentials.get("username") or ""
        return login_count_key(login)
