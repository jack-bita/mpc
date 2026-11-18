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

And one read about the past (SYNC-5): whether a person was working at a given moment, for a record a laptop made
offline, by its own clock (was_working_at): not suspended then, and not yet gone.

A PIN's badge names its job, so it needs no choice of shop. Its shop still comes through a door, the device key's, on
every visit (AUTH-4):

    a badge + the device's key ──▶ the door: which shop? ──▶ that shop open ──▶ its device and job, through the guard
                  no key, or not its own shop's or device's: refused, session.wrong_device
                  shop suspended: refused, shop.suspended
                  device blocked: refused, device.blocked
                  person left, or a new PIN since: None, no job
                  person suspended: refused, staff.suspended
                  password someone else typed: refused, password.must_change
                  ──▶ the staff member, and the device the visit names in both books (X3)

And the device health page's read (SYNC-14, 03 §5.17): each laptop's offline periods of the last week, as it reported
them (outages_this_week). And the workers' page's (PPL-4): every role and extra key each worker was given, for a whole
page of workers at once (given_to); and the job each person who left came back as, once hired again (PPL-11,
current_jobs_of).
"""

import uuid
from collections import defaultdict
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import cast
from zoneinfo import ZoneInfo

from django.views.decorators.debug import sensitive_variables

from apps.control.models import AuditAction, AuditEvent
from apps.core.links import link_type_of
from apps.core.settings_registry import IDLE_MINUTES
from apps.core.tenancy import shop_context
from apps.people.device_keys import hash_device_key
from apps.people.login_doors import shop_of_device_key, shops_of_person
from apps.people.models import (
    Device,
    DeviceOutage,
    DeviceStatus,
    PermissionGrant,
    RoleAssignment,
    StaffMember,
    StaffStatus,
    User,
)
from apps.people.permissions import held_permissions
from apps.shops.models import Shop, ShopStatus, Side
from apps.shops.selectors import get_setting, shop_today


class LoginRefused(Exception):
    # Someone who may not act now, and why. `code` is what the app reads and translates; the message is English, for the
    # logs (ADR-0032). The login class chooses how it answers: a device's refusal is a 401, a session's a 403.
    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


# The audit trail's lines that move a person between active and suspended (02 §5). Leaving, final, is read apart.
_SUSPENSION_MOVES = (AuditAction.STAFF_SUSPEND, AuditAction.STAFF_UNSUSPEND)


def was_working_at(staff: StaffMember, moment: datetime) -> bool:
    """Whether `staff` could work at `moment`: not suspended then, and not yet gone (SYNC-5, X2; Jack: leaving counts
    as suspension does). For a record made offline, by the laptop's clock: the person's status now says nothing of when
    the record was made. Read from the audit trail, which keeps every suspension and return with the server's time (T3),
    and from the person's last day."""
    # Read as stored now, not from the copy handed in: the push reads a record's maker before the record's own
    # transaction, and a leaving recorded in between would be missed (SYNC-5's review).
    status, left_on = StaffMember.objects.filter(pk=staff.pk).values_list("status", "left_on").get()
    if status == StaffStatus.LEFT and moment >= _gone_from(staff, cast(date, left_on)):
        return False
    # The last suspension or return at or before `moment`, if any: a person is born active (02 §5), so none means
    # they were working.
    last = (
        AuditEvent.objects.filter(
            subject_type=link_type_of(staff), subject_id=staff.pk, action__in=_SUSPENSION_MOVES, created_at__lte=moment
        )
        .order_by("-created_at", "-id")
        .values_list("action", flat=True)
        .first()
    )
    return last != AuditAction.STAFF_SUSPEND


def _gone_from(staff: StaffMember, last_day: date) -> datetime:
    # When a person who left stopped working: the earlier of two times. When their leaving was recorded, as it takes
    # effect at once (their PIN stops); or the start of the day after their last day, in the shop's own time zone, as
    # the owner may record on Monday that Friday was the last day, and a Saturday sale is not theirs to make.
    zone = ZoneInfo(staff.shop.timezone)
    after_last_day = datetime.combine(last_day + timedelta(days=1), time.min, tzinfo=zone)
    recorded = (
        AuditEvent.objects.filter(subject_type=link_type_of(staff), subject_id=staff.pk, action=AuditAction.STAFF_LEAVE)
        .values_list("created_at", flat=True)
        .first()
    )
    return after_last_day if recorded is None else min(recorded, after_last_day)


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
    # Someone else typed this person's password (ADR-0038), so until they choose their own, the office routes stay
    # closed to them, whichever way they logged in. Only the way to choose one, and `me`, which tells the app why, stay
    # open, and the counter, on the device's key, goes on working. `user` is read afresh on each visit (the session's
    # person), so this takes effect at once.
    if user.must_change_password:
        raise LoginRefused("This person must choose their own password.", code="password.must_change")


def job_of_person(user: User, *, own_password_needed: bool = True) -> StaffMember | None:
    """The job this person acts in on this visit; None if they have no current job; LoginRefused if they may not act.
    `own_password_needed`: False only on the one route someone on a temporary password may still read."""
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
    if own_password_needed:
        check_own_password(user)
    return staff


def pin_stamp(staff: StaffMember) -> str:
    # When this person's PIN was set, as a badge keeps it: a new PIN ends the badges made with the old one.
    return str(staff.pin_changed_at)


@sensitive_variables()
def job_of_pin_session(
    user: User, badge: Mapping[str, str], device_key: str | None, *, own_password_needed: bool = True
) -> tuple[StaffMember, Device] | None:
    """The job a PIN's badge acts in on this visit (03 §5.9), and the device it stands at, the one holding this key,
    which the visit names in both books (X3, AUTH-8); None if it no longer names a job; LoginRefused if they may not
    act. Every variable hidden from error reports: `device_key` is the device's key itself. `own_password_needed`:
    False only on the one route someone on a temporary password may still read."""
    # Rule 1: a login finds its shop only through a door. This one reads the shop of the device that holds this key, and
    # it must be the shop the badge names. First, as it asks who is calling: someone who copied the badge's number, with
    # no key or another shop's, stops here, with no row read, and is told nothing about the people it names.
    key_hash = None if device_key is None else hash_device_key(device_key)
    shop_id = None if key_hash is None else shop_of_device_key(key_hash)
    if shop_id is None or str(shop_id) != badge["shop"]:
        raise LoginRefused("This session belongs to another device.", code="session.wrong_device")
    with shop_context(shop_id):
        # The key's own device, and it must be the badge's: another laptop of the same shop got this far too.
        device = Device.objects.select_related("shop").filter(pk=badge["device"], key_hash=key_hash).first()
        staff = (
            StaffMember.objects.select_related("shop")
            .filter(pk=badge["staff"], user=user)
            .exclude(status=StaffStatus.LEFT)
            .first()
        )
    if device is None:
        raise LoginRefused("This session belongs to another device.", code="session.wrong_device")
    check_shop_active(device.shop)
    if device.status != DeviceStatus.ACTIVE:
        raise LoginRefused("This device is blocked.", code="device.blocked")
    if staff is None or pin_stamp(staff) != badge["pin_set_at"]:
        return None
    check_may_act(staff)
    if own_password_needed:
        check_own_password(user)
    return staff, device


@dataclass(frozen=True)
class SideKeys:
    # What a person may do on one side, as `me` lists it.
    side: Side
    permissions: list[str]


@dataclass(frozen=True)
class WhoIsHere:
    # Everything `me` answers (apps/people/api/serializers.py).
    user: User
    staff: StaffMember
    shop: Shop
    device: Device | None
    home_side: Side | None
    must_change_password: bool
    idle_minutes: int
    whole_shop: list[str]
    sides: list[SideKeys]


def who_is_here(staff: StaffMember, *, device_id: str | None, idle_minutes: int | None) -> WhoIsHere:
    """Everything the app needs to know about who is logged in here (03 §5.10). `device_id`: the one a PIN's badge
    names; None for a password on a person's own phone. `idle_minutes`: how long that badge lasts unused, which the
    session knows (pin_session_idle_minutes); None for a password, which gets the shop's setting today. The person's
    shop must be open."""
    device = None
    if device_id is not None:
        device = Device.objects.select_related("home_side").filter(pk=device_id).first()
    # Read once, then asked per side: the same few queries however many sides a shop has (PPL-5). HeldPermissions is the
    # one place the rule of 02 §5 is written, so this can't drift from what the routes check.
    held = held_permissions(staff)
    seen = held.sides_seen()
    sides = Side.objects.order_by("code") if seen is None else Side.objects.filter(pk__in=seen).order_by("code")
    return WhoIsHere(
        user=staff.user,
        staff=staff,
        shop=staff.shop,
        device=device,
        home_side=None if device is None else device.home_side,
        must_change_password=staff.user.must_change_password,
        # A PIN's badge: its own minutes. A password: the shop's setting today. A password names no device (ADR-0038),
        # so the server can't tell a person's own phone from the shop's shared laptop, and the laptop locks its screen
        # by these minutes, whoever logged in there and however (UI-4's review).
        idle_minutes=idle_minutes if idle_minutes is not None else idle_lock_minutes(staff.shop),
        whole_shop=sorted(held.on(None)),
        sides=[SideKeys(side=side, permissions=sorted(held.on(side.pk))) for side in sides],
    )


@dataclass(frozen=True)
class GivenRole:
    # One role a worker was given (RoleAssignment), as the workers' page shows it: the role's id, and its template and
    # name, as a copied role's name is empty and the page shows its template's, translated (02 §5); and its side, None
    # for every side.
    id: uuid.UUID
    role: uuid.UUID
    template: str
    name: str
    side: uuid.UUID | None


@dataclass(frozen=True)
class GivenKey:
    # One extra key a worker was given beyond their roles (PermissionGrant), with its side, None for every side.
    id: uuid.UUID
    permission: str
    side: uuid.UUID | None


@dataclass(frozen=True)
class Given:
    # Everything one worker was given, whatever their status: a suspended worker holds none of it now, but holds it all
    # again once brought back, so the page shows it (02 §5).
    roles: list[GivenRole]
    keys: list[GivenKey]


def given_to(staff_ids: Collection[uuid.UUID]) -> dict[uuid.UUID, Given]:
    """Every role and extra key each of these workers was given, by their job's id, in the order given (ids are
    UUIDv7): two queries however many workers, as the workers' page lists them all at once (PPL-4). A worker given
    nothing is there too, with nothing. Through the guarded managers, so only the open shop's rows are read."""
    roles: defaultdict[uuid.UUID, list[GivenRole]] = defaultdict(list)
    keys: defaultdict[uuid.UUID, list[GivenKey]] = defaultdict(list)
    assignments = RoleAssignment.objects.filter(staff_id__in=staff_ids).order_by("id")
    for row_id, staff_id, role_id, template, name, side_id in assignments.values_list(
        "id", "staff_id", "role_id", "role__template", "role__name", "side_id"
    ):
        roles[staff_id].append(GivenRole(id=row_id, role=role_id, template=template, name=name, side=side_id))
    grants = PermissionGrant.objects.filter(staff_id__in=staff_ids).order_by("id")
    for row_id, staff_id, permission, side_id in grants.values_list("id", "staff_id", "permission", "side_id"):
        keys[staff_id].append(GivenKey(id=row_id, permission=permission, side=side_id))
    return {staff_id: Given(roles=roles[staff_id], keys=keys[staff_id]) for staff_id in staff_ids}


def current_jobs_of(person_ids: Collection[uuid.UUID]) -> dict[uuid.UUID, uuid.UUID]:
    """Each of these people's current job at the open shop, one that isn't `left`, by person: what a job that ended
    links to once its person is hired again (PPL-11). One query however many, as the workers' page lists them all at
    once; a person with none is left out. Through the guarded manager, so only the open shop's jobs; one current job
    per person per shop is a database rule (people_staffmember_one_current_job), so a person comes once."""
    current = StaffMember.objects.filter(user_id__in=person_ids).exclude(status=StaffStatus.LEFT)
    return dict(current.values_list("user_id", "id"))


# How far back the health page looks for offline periods (SYNC-14): a week, as the card says, counted back from now
# rather than from a Monday, so on a Monday the page still shows the cuts of the days before; by when the server
# heard of each, on its own clock (Jack, SYNC-14's review).
OUTAGE_WEEK = timedelta(days=7)


def outages_this_week(devices: Sequence[Device], *, now: datetime) -> dict[uuid.UUID, list[DeviceOutage]]:
    """Each device's offline periods the server heard of in the week before `now`, newest first by the laptop's own
    times, by device (SYNC-14): what the health page shows. One query for all of them, through the guarded manager, so
    only the open shop's rows. A device with none is left out of the answer.

    The week is the server's, by when each period reached it (`created_at`), never the laptop's own times (Jack,
    SYNC-14's review): a laptop whose clock battery died, its clock in 2020, still shows today's cut, and one whose
    clock runs months ahead doesn't show every cut it ever sent, for good. A wrong clock is what the page is there to
    show. A period is reported at the laptop's next sync, minutes after it ends, so the week is the same for a laptop
    whose clock is right. The times themselves are the laptop's, as kept (02: DeviceOutage), so a period that ends
    before it starts, after its clock was put back, shows as the laptop said."""
    found: dict[uuid.UUID, list[DeviceOutage]] = {}
    rows = DeviceOutage.objects.filter(device__in=devices, created_at__gte=now - OUTAGE_WEEK).order_by(
        "device_id", "-started_at", "id"
    )
    for row in rows:
        found.setdefault(row.device_id, []).append(row)
    return found
