"""apps/people/selectors.py — the reads that decide who may act: whether a person has a job they can act in today, and
whether a shop is open to anyone (AUTH-3; 03 §5.9; ADR-0038).

A login class only asks these, and turns a refusal into the API's answer. The rules live here so every login follows
the same ones: the password's and the PIN's (apps/people/api/staff_session.py), the device's for its shop
(apps/people/api/authentication.py), and later the choice between two shops (AUTH-7).

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

A PIN's badge needs no door and no choice of shop: it names its job, and the server wrote it at login (AUTH-4):

    a badge ──▶ that shop open ──▶ its device and its job, through the guard
                  not beside its device's key: refused, session.wrong_device
                  shop suspended: refused, shop.suspended
                  device blocked: refused, device.blocked
                  person left, or a new PIN since: None, no job
                  person suspended: refused, staff.suspended
                  password someone else typed: refused, password.must_change
                  ──▶ the staff member
"""

import uuid
from collections.abc import Mapping
from datetime import date
from zoneinfo import ZoneInfo

from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django.views.decorators.debug import sensitive_variables

from apps.core.settings_registry import IDLE_MINUTES
from apps.core.tenancy import shop_context
from apps.people.device_keys import hash_device_key
from apps.people.login_doors import shops_of_person
from apps.people.models import Device, DeviceStatus, StaffMember, StaffStatus, User
from apps.shops.models import Shop, ShopStatus
from apps.shops.selectors import get_setting


class LoginRefused(Exception):
    # Someone who may not act now, and why. `code` is what the app reads and translates; the message is English, for the
    # logs (ADR-0032). The login class chooses how it answers: a device's refusal is a 401, a session's a 403.
    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


def shop_today(shop: Shop) -> date:
    # Today in the shop's own time zone (02 §1), not the server's UTC: at 01:00 in Arusha, UTC is still on yesterday.
    return timezone.localdate(timezone=ZoneInfo(shop.timezone))


def idle_lock_minutes(shop: Shop) -> int:
    """How long a PIN session lasts with no use, as the shop's setting says today (03 §5.9). The shop must be open."""
    return get_setting(IDLE_MINUTES, shop, on=shop_today(shop))


def check_shop_active(shop: Shop) -> None:
    # A suspended shop stops every way in, a person's password and a device's key alike (ADR-0038). Asked as "not
    # active", never as "suspended", so a status a later card adds is refused until that card says otherwise: the login
    # fails closed.
    if shop.status != ShopStatus.ACTIVE:
        raise LoginRefused("This shop is suspended.", code="shop.suspended")


def check_may_act(staff: StaffMember) -> None:
    """Refuse a person who can't act today, whichever way they log in. The shop first: a suspended shop stops everyone,
    whatever each person's own status (ADR-0038). Asked as "not active", so a status a later card adds fails closed."""
    check_shop_active(staff.shop)
    if staff.status != StaffStatus.ACTIVE:
        raise LoginRefused("This person is suspended.", code="staff.suspended")


def check_own_password(user: User) -> None:
    # Someone else typed this person's password (ADR-0038), so until they choose their own, it opens nothing but the way
    # to choose one. `user` is read afresh on each visit (the session's person), so this takes effect at once.
    if user.must_change_password:
        raise LoginRefused("This person must choose their own password.", code="password.must_change")


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
    check_may_act(staff)
    # Last: choosing a password wouldn't let in someone stopped for another reason, so they are told that reason first.
    check_own_password(user)
    return staff


def pin_stamp(staff: StaffMember) -> str:
    # When this person's PIN was set, as a badge keeps it: a new PIN ends the badges made with the old one.
    return str(staff.pin_changed_at)


@sensitive_variables()
def job_of_pin_session(user: User, badge: Mapping[str, str], device_key: str | None) -> StaffMember | None:
    """The job a PIN's badge acts in on this visit (03 §5.9); None if it no longer names one; LoginRefused if they may
    not act. Every variable hidden from error reports: `device_key` is the device's key itself."""
    # The badge's own shop, which the server wrote at login: no door needed, and both rows are read through the guard.
    with shop_context(uuid.UUID(badge["shop"])):
        device = Device.objects.select_related("shop").filter(pk=badge["device"]).first()
        staff = (
            StaffMember.objects.select_related("shop")
            .filter(pk=badge["staff"], user=user)
            .exclude(status=StaffStatus.LEFT)
            .first()
        )
    # First, as it asks who is calling: someone who copied the badge's number is told nothing about the people it names.
    # Compared in constant time, as a key's hash is a secret of the device's.
    if device is None or device_key is None or not constant_time_compare(hash_device_key(device_key), device.key_hash):
        raise LoginRefused("This session belongs to another device.", code="session.wrong_device")
    check_shop_active(device.shop)
    if device.status != DeviceStatus.ACTIVE:
        raise LoginRefused("This device is blocked.", code="device.blocked")
    if staff is None or pin_stamp(staff) != badge["pin_set_at"]:
        return None
    check_may_act(staff)
    check_own_password(user)
    return staff
