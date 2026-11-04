"""apps/people/api/staff_session.py — the office routes' login: a person logged in with a password acts as their staff
member, at their shop (AUTH-3; 03 §5.9; ADR-0038).

allauth's login starts a Django session, which remembers a person: a User, who belongs to no shop. An office route
needs more (CORE-6): the job the person acts in, an Actor (apps/core/tenancy.py) in `request.auth`, which names the shop
the visit works for. StaffSessionAuthentication turns one into the other, on every visit:

    session ──▶ the person ──▶ the door: which shops?         (apps/people/login_doors.py)
                                 none ──▶ no job: office routes refuse, 403 not_authenticated
                                 two  ──▶ 403 staff.choose_shop, until AUTH-7 lets the person choose
                                 one  ──▶ that shop open ──▶ the job, through the guard
                                            shop suspended: 403 shop.suspended
                                            person suspended: 403 staff.suspended
                                            ──▶ request.auth = the staff member

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

from apps.core.tenancy import shop_context
from apps.people.login_doors import shops_of_person
from apps.people.models import StaffMember, StaffStatus, User
from apps.shops.models import ShopStatus


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
        shop_ids = shops_of_person(user.pk)
        if not shop_ids:
            # No current job: the superuser, who is nobody's staff, or someone who has left. Still logged in, but
            # nobody at any shop: `request.auth` stays empty, and every office route refuses (CORE-6).
            return user, None
        if len(shop_ids) > 1:
            # Which shop would this visit work for? Never a guess: the wrong shop's rows would look like the person's
            # own. Refused safely until AUTH-7 lets them choose; nobody works at two shops today (Jack, 3 Nov 2026).
            # English for the logs; the app translates the code (ADR-0032).
            raise exceptions.AuthenticationFailed("This person works at two shops.", code="staff.choose_shop")
        # The job itself, read through the guard inside its shop, which the door named. Opened for this read only: the
        # route opens it again for the whole visit, together with who acts.
        with shop_context(shop_ids[0]):
            staff = (
                StaffMember.objects.select_related("shop").filter(user=user).exclude(status=StaffStatus.LEFT).first()
            )
        if staff is None:
            # Left between the door and this read: no job, as above.
            return user, None
        # Asked as "not active", never as "suspended", so a status a later card adds is refused until that card says
        # otherwise: the login fails closed, as the device's does. The shop first: a suspended shop stops everyone,
        # whatever each person's own status (ADR-0038).
        if staff.shop.status != ShopStatus.ACTIVE:
            raise exceptions.AuthenticationFailed("This shop is suspended.", code="shop.suspended")
        if staff.status != StaffStatus.ACTIVE:
            raise exceptions.AuthenticationFailed("This person is suspended.", code="staff.suspended")
        return user, staff


# drf-spectacular's extension base files each subclass in a registry, in an __init_subclass__ with no type hints, which
# mypy's strict mode refuses to call silently: the library's own untyped code, not ours.
class StaffSessionScheme(SessionScheme):  # type: ignore[no-untyped-call]
    # How the API's schema describes this login: the session cookie, as the library says of DRF's own class. It looks
    # for a login by its exact class, and warns of one it can't describe, which CORE-6's schema test refuses. Here,
    # beside the class, so it is loaded whenever the class is.
    target_class = "apps.people.api.staff_session.StaffSessionAuthentication"
