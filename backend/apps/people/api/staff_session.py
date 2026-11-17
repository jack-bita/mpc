"""apps/people/api/staff_session.py — the office routes' login: a person logged in with a password or a PIN acts as
their staff member, at their shop (AUTH-3, AUTH-4; 03 §5.9; ADR-0038).

A login starts a Django session, which remembers a person: a User, who belongs to no shop. An office route
needs more (CORE-6): the job the person acts in, an Actor (apps/core/tenancy.py) in `request.auth`, which names the shop
the visit works for. StaffSessionAuthentication turns one into the other, on every visit: which job counts, and who is
refused, are rules that every login shares, so they live in apps/people/selectors.py: job_of_person for a password's
session, and job_of_pin_session for a PIN's, which names its own job, shop and device. This class only turns their
answer into DRF's.

On every visit, never only at login: a suspension takes effect on the person's very next request, whatever session they
hold (ADR-0038), and bringing them back needs no new login. The route then opens the shop again for the whole visit
(ShopViewSet, apps/core/api/base.py).

This file owns the two login classes, and their description for the API's schema.
"""

from typing import Any

from drf_spectacular.authentication import SessionScheme
from rest_framework import exceptions
from rest_framework.authentication import SessionAuthentication
from rest_framework.request import Request

from apps.people.api.pin_session import PIN_SESSION, keep_pin_session_alive
from apps.people.device_keys import DEVICE_KEY_COOKIE
from apps.people.models import Device, StaffMember, User
from apps.people.selectors import LoginRefused, job_of_person, job_of_pin_session


class StaffSessionAuthentication(SessionAuthentication):
    # Built on DRF's own session login, which stays what checks the session: the person, who must still be active, and
    # for a change the CSRF token, so another website can't act in the person's name (ADR-0038). No
    # `authenticate_header()`, as DRF's has none: a refused office route answers 403, as CORE-6's do.

    # Does this route need a password of the person's own? Yes, on every route but one (MeSessionAuthentication below).
    own_password_needed = True
    # The device this visit stands at, once its badge has passed its checks, for ShopViewSet to tell PostgreSQL (X3,
    # apps/core/acting.py). None for a password's session, which shows no device: `request.auth` stays the staff member,
    # who names the shop and the person. DRF makes a new login object for each visit, so this never reaches the next.
    device: Device | None = None

    def authenticate(self, request: Request) -> tuple[User, StaffMember | None] | None:
        logged_in: tuple[User, Any] | None = super().authenticate(request)
        if logged_in is None:
            # Nobody logged in, or a person switched off since (User.is_active): no login, as for a stranger.
            return None
        user = logged_in[0]
        # None: no current job. Still logged in, but nobody at any shop: `request.auth` stays empty, and every office
        # route refuses (CORE-6).
        badge = request._request.session.get(PIN_SESSION)
        try:
            if badge is None:
                # A password's session, on a person's own phone.
                return user, job_of_person(user, own_password_needed=self.own_password_needed)
            # The key goes straight from the cookie into the one function that hides it (AUTH-2).
            job = job_of_pin_session(
                user, badge, request.COOKIES.get(DEVICE_KEY_COOKIE), own_password_needed=self.own_password_needed
            )
        except LoginRefused as refused:
            raise exceptions.AuthenticationFailed(str(refused), code=refused.code) from refused
        if job is None:
            return user, None
        staff, self.device = job
        # Only a visit that passes counts as use: a refused one mustn't keep the badge going.
        keep_pin_session_alive(request._request.session)
        return user, staff


class MeSessionAuthentication(StaffSessionAuthentication):
    # The one route someone on a temporary password may still read: the app must be able to ask who they are, to tell
    # them why the office pages are closed (Jack, 4 Nov 2026). Everything else still applies.
    own_password_needed = False


# drf-spectacular's extension base files each subclass in a registry, in an __init_subclass__ with no type hints, which
# mypy's strict mode refuses to call silently: the library's own untyped code, not ours.
class StaffSessionScheme(SessionScheme):  # type: ignore[no-untyped-call]
    # How the API's schema describes this login: the session cookie, as the library says of DRF's own class. It looks
    # for a login by its exact class, and warns of one it can't describe, which CORE-6's schema test refuses. Here,
    # beside the class, so it is loaded whenever the class is.
    target_class = "apps.people.api.staff_session.StaffSessionAuthentication"
