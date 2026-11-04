"""apps/people/selectors.py — the reads that decide who may act: whether a person has a job they can act in today, and
whether a shop is open to anyone (AUTH-3; 03 §5.9; ADR-0038).

A login class only asks these, and turns a refusal into the API's answer. The rules live here so every login follows
the same ones: the password's today (apps/people/api/staff_session.py), the device's for its shop
(apps/people/api/authentication.py), and later the PIN's (AUTH-4) and the choice between two shops (AUTH-7).

    a person ──▶ the door: which shops?         (apps/people/login_doors.py)
                   none ──▶ None: no job, so office routes refuse
                   two  ──▶ refused, staff.choose_shop, until AUTH-7 lets the person choose
                   one  ──▶ that shop open ──▶ the job, through the guard
                              shop suspended: refused, shop.suspended
                              person suspended: refused, staff.suspended
                              password someone else typed: refused, password.must_change
                              ──▶ the staff member

A person who has left counts as no job, not as refused: they aren't anyone at that shop now. A suspended person's job
still counts, so they can be told why they are stopped.
"""

from apps.core.tenancy import shop_context
from apps.people.login_doors import shops_of_person
from apps.people.models import StaffMember, StaffStatus, User
from apps.shops.models import Shop, ShopStatus


class LoginRefused(Exception):
    # Someone who may not act now, and why. `code` is what the app reads and translates; the message is English, for the
    # logs (ADR-0032). The login class chooses how it answers: a device's refusal is a 401, a session's a 403.
    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


def check_shop_active(shop: Shop) -> None:
    # A suspended shop stops every way in, a person's password and a device's key alike (ADR-0038). Asked as "not
    # active", never as "suspended", so a status a later card adds is refused until that card says otherwise: the login
    # fails closed.
    if shop.status != ShopStatus.ACTIVE:
        raise LoginRefused("This shop is suspended.", code="shop.suspended")


def job_of_person(user: User) -> StaffMember | None:
    """The job this person acts in on this visit; None if they have no current job; LoginRefused if they may not act."""
    shop_ids = shops_of_person(user.pk)
    if not shop_ids:
        # The superuser, who is nobody's staff, or someone who has left.
        return None
    if len(shop_ids) > 1:
        # Which shop would this visit work for? Never a guess: the wrong shop's rows would look like the person's own.
        # Refused safely until AUTH-7 lets them choose; nobody works at two shops today (Jack, 3 Nov 2026).
        raise LoginRefused("This person works at two shops.", code="staff.choose_shop")
    # The job itself, read through the guard inside its shop, which the door named. Opened for this read only: the route
    # opens it again for the whole visit, together with who acts.
    with shop_context(shop_ids[0]):
        staff = StaffMember.objects.select_related("shop").filter(user=user).exclude(status=StaffStatus.LEFT).first()
    if staff is None:
        # Left between the door and this read: no job, as above.
        return None
    # The shop first: a suspended shop stops everyone, whatever each person's own status (ADR-0038).
    check_shop_active(staff.shop)
    # Asked as "not active" too, for the same reason as the shop.
    if staff.status != StaffStatus.ACTIVE:
        raise LoginRefused("This person is suspended.", code="staff.suspended")
    # Last: choosing a password wouldn't let in someone stopped for another reason, so they are told that reason first.
    # Someone else typed this person's password (ADR-0038), so until they choose their own, it opens nothing but the way
    # to choose one. `user` is read afresh on each visit (the session's person), so this takes effect at once.
    if user.must_change_password:
        raise LoginRefused("This person must choose their own password.", code="password.must_change")
    return staff
