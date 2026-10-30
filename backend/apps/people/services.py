"""apps/people/services.py — every write to the people tables, one function per action (ADR-0015).

A staff member's working life at one shop (02 §5): they are added, suspended, brought back and marked
as left, and given a PIN (set_pin; apps/people/pins.py hashes it). And what they may do there: a shop gets
its own copy of the role templates (copy_role_templates; set_up_shop makes a whole new shop with them),
and a person is given a role, or one extra permission, on one side or on all of them (assign_role,
grant_permission), by someone who may give it. And the shop's devices (AUTH-1, 03 §5.9): a new device asks to join
(start_pairing), and a manager with device.manage says yes (confirm_pairing).
Each action runs in one transaction, checks that every row it links to belongs to the same shop (T1),
and refuses a broken rule with a ValidationError that carries a code (ADR-0032); CORE-6's error handler
will turn it into the API's error shape. A status change also writes its line in the audit trail, with
who and why, in the same transaction (apps/control/services.py, audit): the change and its line are kept
together or not at all (T3).

Callers open shop_context(shop) first: full_clean and the unique checks read through the guarded
`objects` (CORE-2).
"""

import uuid
from collections.abc import Collection, Sequence
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import date
from zoneinfo import ZoneInfo

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.control.models import AuditAction
from apps.control.services import audit
from apps.core.acting import acting_as
from apps.core.models import SequenceName, ShopScoped
from apps.core.permissions import ROLE_TEMPLATES, Permission
from apps.core.sequences import next_number
from apps.core.tenancy import ALL_SHOPS, current_shop, shop_context
from apps.people.device_keys import (
    PAIRING_CODE_LIFETIME,
    clean_typed_code,
    hash_device_key,
    make_device_key,
    make_pairing_code,
)
from apps.people.models import (
    Device,
    PairingRequest,
    PermissionGrant,
    Role,
    RoleAssignment,
    StaffMember,
    StaffStatus,
    User,
)
from apps.people.permissions import effective_permissions, require
from apps.people.pins import check_pin_strength, hash_pin
from apps.shops.models import Shop, Side
from apps.shops.services import NewSide, create_shop


def _check_shop(shop_id: uuid.UUID, by: StaffMember | None) -> None:
    # T1: an action works inside one shop, on that shop's rows only. The guard watches reads, not writes
    # (CORE-2), so both checks are the services' own.
    # 1. The shop acted on is the one this visit opened (shop_context). Without this, code inside shop
    #    A's visit could write into shop B, and full_clean's unique checks would read A's rows, so a
    #    clash in B would end as a database error. A system job, under system_context(), has every shop
    #    open. No shop open at all raises NoShopSelected.
    open_shop = current_shop()
    if open_shop is not ALL_SHOPS and open_shop != shop_id:
        raise ValidationError("This shop is not the one open.", code="staff.other_shop")
    # 2. The person acting belongs to that shop too: a manager of shop B named here would get past the guard.
    if by is not None and by.shop_id != shop_id:
        raise ValidationError("The person acting belongs to another shop.", code="staff.other_shop")


def _shop_today(shop: Shop) -> date:
    # Today in the shop's own time zone (02 §1), not the server's UTC: at 01:00 in Arusha, UTC is still
    # on yesterday.
    return timezone.localdate(timezone=ZoneInfo(shop.timezone))


def add_staff(
    *,
    shop: Shop,
    user: User,
    display_name: str,
    job_title: str = "",
    started_on: date | None = None,
    by: StaffMember | None,
) -> StaffMember:
    """Give a person a job at a shop. `by`: who adds them; None for the system or the superuser."""
    _check_shop(shop.pk, by)
    if started_on is None:
        started_on = _shop_today(shop)
    staff = StaffMember(
        shop=shop,
        user=user,
        display_name=display_name,
        job_title=job_title,
        started_on=started_on,
        created_by=by,
    )
    with transaction.atomic():
        # Every field, clean() and the rules in Meta, before anything is written: a clash comes back
        # as a code. Two adds at the very same moment can both pass this; the database's unique
        # index then refuses the second.
        staff.full_clean()
        staff.save()
    return staff


def _check_reason(reason: str) -> None:
    # Rule 7: a suspension or a leaving is always recorded with who, when and why. Checked before anything
    # is locked; audit() keeps the reason, trimmed, in the action's own line (CTRL-2).
    if not reason.strip():
        raise ValidationError("A reason is required.", code="staff.reason_required")


def _save(staff: StaffMember, *, by: StaffMember | None, fields: list[str]) -> None:
    # Saves the changed fields, with `by` told to PostgreSQL for the save: the history line its trigger writes then
    # names the same person as the action's audit line, even outside an office visit, as in a job or a command
    # (02 v1.7: one fact, one answer; apps/core/acting.py). With `by` None, the system acts, and nobody is told.
    with acting_as(by) if by is not None else nullcontext():
        staff.save(update_fields=fields)


def _locked(staff: StaffMember) -> StaffMember:
    # The row read again, and locked until the transaction ends (SELECT ... FOR UPDATE). Two managers
    # acting on Asha at the same moment take turns, and the second sees what the first one wrote, not
    # the old copy on their screen.
    return StaffMember.objects.select_for_update().get(pk=staff.pk)


def suspend(staff: StaffMember, *, by: StaffMember | None, reason: str) -> StaffMember:
    """Stop an active person working for a while. Their PIN stops working (AUTH-4)."""
    _check_shop(staff.shop_id, by)
    _check_reason(reason)
    with transaction.atomic():
        staff = _locked(staff)
        if staff.status != StaffStatus.ACTIVE:
            raise ValidationError("Only an active staff member can be suspended.", code="staff.not_active")
        staff.status = StaffStatus.SUSPENDED
        staff.full_clean()
        _save(staff, by=by, fields=["status"])
        # In the same transaction: if the line can't be written, the suspension is undone with it.
        audit(
            action=AuditAction.STAFF_SUSPEND,
            subject=staff,
            reason=reason,
            by=by,
            before={"status": StaffStatus.ACTIVE},
            after={"status": StaffStatus.SUSPENDED},
        )
    return staff


def unsuspend(staff: StaffMember, *, by: StaffMember | None, reason: str) -> StaffMember:
    """Let a suspended person work again."""
    _check_shop(staff.shop_id, by)
    _check_reason(reason)
    with transaction.atomic():
        staff = _locked(staff)
        if staff.status != StaffStatus.SUSPENDED:
            raise ValidationError("Only a suspended staff member can come back.", code="staff.not_suspended")
        staff.status = StaffStatus.ACTIVE
        staff.full_clean()
        _save(staff, by=by, fields=["status"])
        audit(
            action=AuditAction.STAFF_UNSUSPEND,
            subject=staff,
            reason=reason,
            by=by,
            before={"status": StaffStatus.SUSPENDED},
            after={"status": StaffStatus.ACTIVE},
        )
    return staff


def mark_left(staff: StaffMember, *, left_on: date, by: StaffMember | None, reason: str) -> StaffMember:
    """Record that a person left on `left_on`. Final: if they come back, add_staff gives them a new job."""
    _check_shop(staff.shop_id, by)
    _check_reason(reason)
    # On their last day or after, never ahead (Jack, 27 Oct): `left` takes effect at once, so "leaves on
    # Friday" typed on Monday would stop their PIN four days early.
    if left_on > _shop_today(staff.shop):
        raise ValidationError("A leaving date can't be in the future.", code="staff.left_in_future")
    with transaction.atomic():
        staff = _locked(staff)
        if staff.status == StaffStatus.LEFT:
            raise ValidationError("This person has already left.", code="staff.left")
        # Active or suspended: a suspended person can leave too, and the line says which they were.
        before = {"status": staff.status, "left_on": staff.left_on}
        staff.status = StaffStatus.LEFT
        staff.left_on = left_on
        # The rules in Meta refuse a leaving date before the start date (staff.left_before_start).
        staff.full_clean()
        _save(staff, by=by, fields=["status", "left_on"])
        audit(
            action=AuditAction.STAFF_LEAVE,
            subject=staff,
            reason=reason,
            by=by,
            before=before,
            after={"status": StaffStatus.LEFT, "left_on": left_on},
        )
    return staff


def set_pin(staff: StaffMember, pin: str, *, by: StaffMember | None) -> StaffMember:
    """Give a person a new PIN, online only (03 §5.9). Devices see the new `pin_changed_at` at their next
    sync and drop their old offline check."""
    _check_shop(staff.shop_id, by)
    check_pin_strength(pin)
    # Hashed before the lock: Argon2 is slow on purpose, and the row stays locked only for the short
    # write below.
    pin_hash = hash_pin(pin)
    with transaction.atomic():
        staff = _locked(staff)
        if staff.status == StaffStatus.LEFT:
            raise ValidationError("A person who has left can't be given a PIN.", code="staff.left")
        staff.pin_hash = pin_hash
        staff.pin_changed_at = timezone.now()
        staff.full_clean()
        _save(staff, by=by, fields=["pin_hash", "pin_changed_at"])
    return staff


def set_up_shop(*, name: str, code: str, sides: Sequence[NewSide]) -> Shop:
    """Make a live shop with everything it needs to work, all or nothing: its sides, each with its stock location
    and cash drawer (create_shop, apps/shops/services.py), and its own copy of the six roles. For the superuser and
    system jobs. `shops` may not import `people` (ADR-0035), so the roles are added here, not by create_shop: a
    shop made by create_shop alone has no roles, so nobody may act there."""
    # One transaction around both: if the roles can't be copied, the shop and its sides are taken back too.
    with transaction.atomic():
        shop = create_shop(name=name, code=code, sides=sides)
        # create_shop closes the new shop as it returns; the roles' checks read through the guard, so it is opened
        # again for them.
        with shop_context(shop):
            copy_role_templates(shop)
    return shop


def copy_role_templates(shop: Shop) -> dict[str, Role]:
    """Give a shop its own copy of the six role templates (apps/core/permissions.py), as Role rows its owner can
    change later, by their template's code: roles["manager"]. Once per shop: a second copy is refused
    (role.template_taken). Made by the system: a new shop has no staff yet, so `created_by` is empty (02 §1)."""
    _check_shop(shop.pk, None)
    roles: dict[str, Role] = {}
    # One transaction: a shop gets all six roles, or none.
    with transaction.atomic():
        for template, codes in ROLE_TEMPLATES.items():
            # Sorted: the same order in every shop, in the history and on the screens, whatever order a set gives.
            role = Role(shop=shop, template=template, permissions=sorted(codes))
            role.full_clean()
            role.save()
            roles[template] = role
    return roles


def _check_same_shop(staff: StaffMember, *rows: ShopScoped | None) -> None:
    # T1: what a person is given belongs to their own shop. The guard watches reads, not writes (CORE-2): shop B's
    # role or side given at shop A would sit in A's rows, pointing at rows A's guard never shows.
    if any(row is not None and row.shop_id != staff.shop_id for row in rows):
        raise ValidationError("This belongs to another shop.", code="staff.other_shop")


def _check_giver(by: StaffMember | None, codes: Collection[str], side: Side | None) -> None:
    # Who may give (Jack, 29 Oct 2026). `by` None: the system or the superuser, who set up the shop's first owner.
    # Anyone else needs staff.manage on that side, and may give only codes they hold there themselves: Baba hands a
    # manager staff.manage to add a loader, and that manager still can't make himself Owner and approve his own day.
    # Both checks use one reading of the giver's roles, from the database (apps/people/permissions.py), so a giver
    # suspended a moment ago gives nothing.
    if by is None:
        return
    held = effective_permissions(by, side)
    if Permission.STAFF_MANAGE not in held:
        raise PermissionDenied("Giving a role or a permission needs staff.manage on that side.")
    # Only codes from the list are compared: one that isn't is the table's own rule to refuse, with its code
    # (permission.unknown), whoever sends it. A typo is reported as a typo.
    known = {code for code in codes if code in Permission.values}
    if not known <= held:
        raise PermissionDenied("Nobody gives a permission they don't hold on that side.")


def _locked_receiver(staff: StaffMember) -> StaffMember:
    # The person read again and locked (_locked), so a leaving recorded at the same moment either comes first, and is
    # refused here, or waits until this is given. A person who has left gets nothing: a worker who comes back gets a
    # new job (02 §5). A suspended one may: it counts once they are brought back.
    staff = _locked(staff)
    if staff.status == StaffStatus.LEFT:
        raise ValidationError("A person who has left can't be given a role or a permission.", code="staff.left")
    return staff


def assign_role(staff: StaffMember, role: Role, *, side: Side | None, by: StaffMember | None) -> RoleAssignment:
    """Give a person a role on one side, or on every side (`side=None`), a side added later included. `by`: who
    gives it; None for the system or the superuser."""
    _check_shop(staff.shop_id, by)
    _check_same_shop(staff, role, side)
    with transaction.atomic():
        staff = _locked_receiver(staff)
        # The role as stored, read again and locked: the giver's check compares its saved codes, never those of the
        # copy handed in, which may have been changed in memory and never saved (the Owner role made to say
        # "sale.write" would pass as a Seller's). An owner changing the role at the same moment waits until it is
        # given, or this waits for them.
        role = Role.objects.select_for_update().get(pk=role.pk)
        _check_giver(by, role.permissions, side)
        given = RoleAssignment(shop_id=staff.shop_id, staff=staff, role=role, side=side, created_by=by)
        # Every rule in Meta first: the same role twice on one side comes back as a code (role.already_given).
        given.full_clean()
        given.save()
    return given


def grant_permission(
    staff: StaffMember, permission: str, *, side: Side | None, by: StaffMember | None
) -> PermissionGrant:
    """Give a person one extra permission on one side, or on every side (`side=None`): Juma may count the stock on
    Vyakula. Checked as a role is given (assign_role)."""
    _check_shop(staff.shop_id, by)
    _check_same_shop(staff, side)
    _check_giver(by, [permission], side)
    with transaction.atomic():
        staff = _locked_receiver(staff)
        granted = PermissionGrant(shop_id=staff.shop_id, staff=staff, permission=permission, side=side, created_by=by)
        # A code from the list only (permission.unknown), and once per side (permission.already_given).
        granted.full_clean()
        granted.save()
    return granted


@dataclass(frozen=True)
class NewPairing:
    # What a device that asks to join gets back (start_pairing): its waiting request, whose `code` it shows on screen,
    # and its key. The key is handed over once, here, and kept nowhere on the server but as its hash: AUTH-2 puts it in
    # the device's cookie.
    request: PairingRequest
    key: str


# How many codes start_pairing draws before it gives up. A clash with a code already given is about 1 in a million
# even after a million asks, so a fifth clash in a row would mean a bug, not bad luck.
_CODE_DRAWS = 5


def start_pairing() -> NewPairing:
    """A new device asks to join a shop (03 §5.9, step 1). It gets a code to show and its key, which opens nothing
    until a manager confirms the code (confirm_pairing). Needs no shop open: the device belongs to no shop yet, and
    the request it waits in has none (02 v1.11)."""
    # The key is made here, by the device's own request, not when the manager confirms: confirming happens on the
    # manager's phone, which must never hold the device's key, and the server never keeps it in plain text, not even
    # until the device comes to collect it (Jack, AUTH-1).
    key = make_device_key()
    for _ in range(_CODE_DRAWS):
        request = PairingRequest(
            code=make_pairing_code(),
            expires_at=timezone.now() + PAIRING_CODE_LIFETIME,
            key_hash=hash_device_key(key),
        )
        try:
            # A savepoint of its own: a clash undoes only this insert, even inside a caller's transaction.
            with transaction.atomic():
                request.save()
        except IntegrityError:
            # Only a code already given (people_pairingrequest_code_once) is drawn again. Any other broken rule is a
            # bug in this code, and is raised as it is.
            if PairingRequest.objects.filter(code=request.code).exists():
                continue
            raise
        return NewPairing(request=request, key=key)
    raise RuntimeError(f"No free pairing code after {_CODE_DRAWS} draws.")


def confirm_pairing(code: str, *, name: str, home_side: Side, by: StaffMember) -> Device:
    """A manager says yes to a waiting device (03 §5.9, step 2): they type the code it shows, name it and pick its home
    side. The device is made in their own shop, active, with the shop's next device code and the key's hash, so its
    key works from now on. `by` is always a person, who needs device.manage on `home_side`. Refusals: the code
    unknown, used or expired (pairing.code_unknown, .code_used, .code_expired); a name the shop already gives another
    device (device.name_taken)."""
    _check_shop(by.shop_id, by)
    # T1: a device of this shop lives on a side of this shop.
    _check_same_shop(by, home_side)
    # The permission first, before the code is even looked at: someone without device.manage learns nothing about
    # which codes are waiting (PermissionDenied, 403).
    require(by, Permission.DEVICE_MANAGE, home_side)
    with transaction.atomic():
        try:
            # Read and locked until this transaction ends, so two managers typing the same code at once take turns,
            # and the second finds it used.
            request = PairingRequest.objects.select_for_update().get(code=clean_typed_code(code))
        except PairingRequest.DoesNotExist:
            raise ValidationError("No device is waiting with this code.", code="pairing.code_unknown") from None
        # Used is checked before expired: a code used and then gone stale was used, which is what the manager needs.
        if request.device_id is not None:
            raise ValidationError("This code was already used.", code="pairing.code_used")
        now = timezone.now()
        if request.expires_at <= now:
            raise ValidationError("This code has expired: ask the device for a new one.", code="pairing.code_expired")
        device = Device(
            shop_id=by.shop_id,
            name=name,
            home_side=home_side,
            # D7: the shop's next device code. If anything below refuses, the transaction rolls back, and the number
            # with it: nothing kept it, so the next device gets it (apps/core/sequences.py).
            code=next_number(by.shop_id, SequenceName.DEVICE),
            key_hash=request.key_hash,
            created_by=by,
        )
        # Every field, clean() and the rules in Meta, before anything is written: a name the shop already uses comes
        # back as device.name_taken, and the code stays waiting for a better name.
        device.full_clean()
        device.save()
        request.device = device
        request.confirmed_at = now
        request.save(update_fields=["device", "confirmed_at"])
    return device
