"""apps/people/api/staff_session.py — the office routes' login: a person logged in with a password acts as their staff
member, at their shop (AUTH-3; 03 §5.9; ADR-0038).

allauth's login starts a Django session, which remembers a person: a User, who belongs to no shop. An office route
needs more (CORE-6): the job the person acts in, an Actor (apps/core/tenancy.py) in `request.auth`, which names the shop
the visit works for. StaffSessionAuthentication turns one into the other, on every visit: which job counts, and who is
refused, are rules that every login shares, so they live in job_of_person (apps/people/selectors.py). This class only
turns its answer into DRF's.

On every visit, never only at login: a suspension takes effect on the person's very next request, whatever session they
hold (ADR-0038), and bringing them back needs no new login. The route then opens the shop again for the whole visit
(ShopViewSet, apps/core/api/base.py).

This file owns the login class and its description for the API's schema.
"""

from typing import Any

from drf_spectacular.authentication import SessionScheme
from rest_framework import exceptions
from rest_framework.authentication import SessionAuthentication
from rest_framework.request import Request

from apps.people.models import StaffMember, User
from apps.people.selectors import LoginRefused, job_of_person


class StaffSessionAuthentication(SessionAuthentication):
    # Built on DRF's own session login, which stays what checks the session: the person, who must still be active, and
    # for a change the CSRF token, so another website can't act in the person's name (ADR-0038). No
    # `authenticate_header()`, as DRF's has none: a refused office route answers 403, as CORE-6's do.

    def authenticate(self, request: Request) -> tuple[User, StaffMember | None] | None:
        logged_in: tuple[User, Any] | None = super().authenticate(request)
        if logged_in is None:
            # Nobody logged in, or a person switched off since (User.is_active): no login, as for a stranger.
            return None
        user = logged_in[0]
        try:
            # None: no current job. Still logged in, but nobody at any shop: `request.auth` stays empty, and every
            # office route refuses (CORE-6).
            return user, job_of_person(user)
        except LoginRefused as refused:
            raise exceptions.AuthenticationFailed(str(refused), code=refused.code) from refused


# drf-spectacular's extension base files each subclass in a registry, in an __init_subclass__ with no type hints, which
# mypy's strict mode refuses to call silently: the library's own untyped code, not ours.
class StaffSessionScheme(SessionScheme):  # type: ignore[no-untyped-call]
    # How the API's schema describes this login: the session cookie, as the library says of DRF's own class. It looks
    # for a login by its exact class, and warns of one it can't describe, which CORE-6's schema test refuses. Here,
    # beside the class, so it is loaded whenever the class is.
    target_class = "apps.people.api.staff_session.StaffSessionAuthentication"
