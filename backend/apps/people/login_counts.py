"""apps/people/login_counts.py — allauth's count of a person's wrong passwords: who it counts against, and how it is
forgotten (AUTH-3, AUTH-6; ADR-0038).

allauth slows guessers down by counting wrong passwords per login name, 5 in 5 minutes *(its defaults)*, in a cache
table of their own. This file owns the name each count is kept under, and lifts a person's count when someone else sets
their password. On its own, so the services and the admin can lift a count without importing allauth's adapter and
checker (apps/people/accounts.py), which reads the same names.
"""

from allauth.core.internal.ratelimit import get_cache_key, get_rates
from django.core.cache import cache
from django.utils.crypto import salted_hmac

from apps.people.models import User


def login_count_key(login: str) -> str:
    """Who allauth counts wrong passwords against: the login name, whichever it is, in its stored form, so each
    person's count is their own."""
    # A fingerprint made with the server's secret key: allauth writes only a plain hash of this into the row's key, and
    # a plain hash of a phone number can be worked back, by trying every number.
    return salted_hmac("login.person", login.lower(), algorithm="sha256").hexdigest()


def lift_wrong_password_count(user: User) -> None:
    """Forget this person's own count of wrong passwords, for each name they log in by. For a password set by someone
    else (set_temporary_password, apps/people/services.py; the admin's forms): the person who forgot has usually typed
    it wrong a few times, and the new one must work at once, not after 5 minutes standing in front of the owner."""
    # allauth's own clear also lifts the caller's count, by their network, and so needs a request, which a service has
    # none of. Here the caller is the owner: their network's count isn't the person's. So only the counts kept per login
    # name are lifted. allauth's internal helpers name those rows, so a later allauth could move them, and this would
    # stop working unseen: test_temporary_password_lifts_the_wrong_password_count pins it.
    for login in (user.email, user.phone):
        if login:
            for rate in get_rates(app="allauth.account", action="login_failed"):
                if rate.per == "key":
                    row = get_cache_key(
                        None, app="allauth.account", action="login_failed", rate=rate, key=login_count_key(login)
                    )
                    cache.delete(row)
