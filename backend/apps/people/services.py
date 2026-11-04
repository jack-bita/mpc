"""apps/people/services.py — every write to the people tables, one function per action (ADR-0015).

A staff member's working life at one shop (02 §5): they are added, suspended, brought back and marked
as left, and given a PIN (set_pin; apps/people/pins.py hashes it) or a temporary password, face to face
(set_temporary_password, AUTH-6). And what they may do there: a shop gets
its own copy of the role templates (copy_role_templates; set_up_shop makes a whole new shop with them),
and a person is given a role, or one extra permission, on one side or on all of them (assign_role,
grant_permission), by someone who may give it. And the shop's devices (AUTH-1, 03 §5.9): a new device asks to join
(start_pairing), a manager with device.manage says yes (confirm_pairing), renames it (rename_device, AUTH-5), and
blocks it, or lets it work again (block, unblock); and each time its key reaches the server, it is noted as seen
(note_device_seen, AUTH-2).
Each action runs in one transaction, checks that every row it links to belongs to the same shop (T1),
and refuses a broken rule with a ValidationError that carries a code (ADR-0032); CORE-6's error handler
will turn it into the API's error shape. A status change also writes its line in the audit trail, with
who and why, in the same transaction (apps/control/services.py, audit): the change and its line are kept
together or not at all (T3).

Callers open shop_context(shop) first: full_clean and the unique checks read through the guarded
`objects` (CORE-2). The one exception is start_pairing: a device that asks to join belongs to no shop yet,
so it needs none open, and its request links to nothing (02 v1.11).
"""

import uuid
from collections.abc import Collection, Sequence
from contextlib import nullcontext
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from django.contrib.auth.hashers import make_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables

from apps.control.models import AuditAction, AuditEvent
from apps.control.services import audit
from apps.core.acting import acting_as
from apps.core.editing import editing
from apps.core.links import link_type_of
from apps.core.models import SequenceName, ShopScoped
from apps.core.permissions import ROLE_TEMPLATES, HeldPermissions, Permission, RoleTemplate
from apps.core.sequences import next_number
from apps.core.tenancy import ALL_SHOPS, current_shop, shop_context
from apps.people.accounts import lift_wrong_password_count
from apps.people.device_keys import (
    PAIRING_CODE_LIFETIME,
    clean_typed_code,
    hash_device_key,
    make_device_key,
    make_pairing_code,
)
from apps.people.login_doors import shop_of_device_key
from apps.people.models import (
    Device,
    DeviceStatus,
    PairingRequest,
    PermissionGrant,
    Role,
    RoleAssignment,
    StaffMember,
    StaffStatus,
    User,
)
from apps.people.permissions import effective_permissions, given_permissions, held_permissions, require
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


def _check_reason(reason: str, *, code: str = "staff.reason_required") -> None:
    # Rule 7: a suspension, a leaving or a device's block is always recorded with who, when and why. Checked
    # before anything is locked; audit() keeps the reason, trimmed, in the action's own line (CTRL-2). `code`
    # names what needs the reason, so the screen says it in its own words (ADR-0032).
    if not reason.strip():
        raise ValidationError("A reason is required.", code=code)


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


# Every variable shows as stars in Django's error reports, which list each function's variables when something fails,
# here and in everything this calls. Hiding `password` by its name wouldn't do: the library at the bottom of the hash
# names it `secret`, and running out of memory there is the likeliest crash on the demo's 512 MB. A crash here shows its
# lines, only not its values.
@sensitive_variables()
def set_temporary_password(staff: StaffMember, password: str, *, by: StaffMember, reason: str) -> None:
    """Set a first or forgotten password, face to face (ADR-0038): Baba types one for Asha and tells it to her. She logs
    in with it, and every office route refuses her until she chooses her own (apps/people/selectors.py). `by` is always
    a person, who needs staff.manage on the whole shop, as a password opens the whole person. Refusals, each a code the
    screen translates: the password's checks, under `password`; staff.reason_required; staff.left; and who may
    (_check_may_set_password). Her older logins end, as each holds a fingerprint of the password it started with, so a
    lost phone is logged out. Returns nothing: the password goes no further than this function (no answer, log or audit
    line holds it)."""
    _check_shop(staff.shop_id, by)
    _check_reason(reason)
    # Who may, first, before the password is even looked at: a refused try pays for no slow hash, and this route has no
    # limit to slow one down. Asked again under the locks below, as this copy can be out of date by then.
    _check_may_set_password(staff, staff.user, by=by)
    # allauth's login takes the spaces off both ends of what is typed. A password stored with them could never match, so
    # she would use up her five tries on what Baba's keyboard added. Taken off before the checks, so they judge what
    # will really be stored: twelve spaces are nothing at all.
    password = password.strip()
    try:
        # Like any other password: it opens a real login until she replaces it. It reads her name and phone, as a
        # password too like them is refused.
        validate_password(password, staff.user)
    except ValidationError as refused:
        # Filed under the field, so the screen shows it beside the box the owner typed in. from None: the refused
        # error's own frames, which hold the password, stay out of the chain.
        raise ValidationError({"password": refused.error_list}) from None
    # Hashed before the lock, as set_pin does: Argon2 is slow on purpose, and the rows stay locked only for the short
    # write below. make_password, not user.set_password: that keeps the typed password on the row in memory until save.
    encoded = make_password(password)
    with transaction.atomic():
        # Her job, the job of the one acting, and her person, read again and locked. A role given to her, a leaving
        # recorded, or a suspension of the one acting, at this same moment, comes first and is seen here, or waits until
        # this is done: the hash above left plenty of time for one. In id order, so two people each setting the other's
        # password at once take turns, and never wait for each other for good.
        rows = StaffMember.objects.select_for_update().filter(pk__in=[staff.pk, by.pk]).order_by("pk")
        jobs = {job.pk: job for job in rows}
        staff, by = jobs[staff.pk], jobs[by.pk]
        user = User.objects.select_for_update().get(pk=staff.user_id)
        _check_may_set_password(staff, user, by=by)
        was_marked = user.must_change_password
        # Past AccountAdapter.set_password, which is for a person choosing their own, and takes the mark off.
        user.password = encoded
        user.must_change_password = True
        user.save(update_fields=["password", "must_change_password"])
        # In the same transaction: if the line can't be written, the password isn't changed either (T3). Only the mark
        # goes in the line: never the password, nor its hash, which could be attacked by anyone reading the trail.
        audit(
            action=AuditAction.STAFF_TEMPORARY_PASSWORD,
            subject=staff,
            reason=reason,
            by=by,
            before={"must_change_password": was_marked},
            after={"must_change_password": True},
        )
    # Outside the transaction: it is a cache row, and needs no lock. If this fails, the password is set, and the person
    # waits out the 5 minutes.
    lift_wrong_password_count(user)


def _check_may_set_password(staff: StaffMember, user: User, *, by: StaffMember) -> None:
    # Whoever sets a person's password can log in as them. So this is the giver rule (02 §5), for a whole person: Baba
    # may hand a manager staff.manage to deal with a forgotten password, and that manager still can't become anyone
    # stronger than himself (Jack, 4 Nov 2026). Refused as a ValidationError with its code, as flag.own_flag is, so the
    # screen can say what to do.
    # The key, on the whole shop, read afresh: a giver suspended a moment ago holds nothing (PermissionDenied, 403).
    require(by, Permission.STAFF_MANAGE, None)
    if staff.status == StaffStatus.LEFT:
        raise ValidationError("A person who has left can't be given a password.", code="staff.left")
    if staff.pk == by.pk:
        # A thief holding a logged-in phone could set a new password for its owner, with no current one, and keep the
        # login for good. A person changes their own by allauth's change route, which asks for the current one.
        raise ValidationError("A person changes their own password with the current one.", code="password.own")
    # The superuser's alone (ADR-0038). Read from the roles, whatever the person's status: a suspended owner holds no
    # keys but is still the owner, and two owners may have fallen out with each other. When PPL-4 adds an end to a role,
    # an ended Owner role must stop counting here too.
    is_owner = RoleAssignment.objects.filter(staff=staff, role__template=RoleTemplate.OWNER).exists()
    # Their password opens the admin, which reads every shop's rows: no shop's owner hands that out. A job at another
    # shop isn't looked at: reading that shop's rows during this shop's visit would pass the guard, which is only for a
    # login, before any shop is open (ADR-0037, Jack, 4 Nov 2026). Nothing is lost yet, as a person at two shops is
    # refused at every office route until AUTH-7, whose card adds this rule.
    if is_owner or user.is_superuser or user.is_staff:
        raise ValidationError("Only the superuser may reset this person's password.", code="password.superuser_only")
    # What the person was given, whatever their status, as they hold it all again once brought back; against what the
    # one acting holds now.
    if not held_permissions(by).covers(given_permissions(staff)):
        raise ValidationError("This person holds a key the one acting doesn't.", code="password.more_keys")


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


def _check_no_open_temporary_password(staff: StaffMember, codes: Collection[str], side: Side | None) -> None:
    # The trap (Jack, 4 Nov 2026): Meneja set Juma's temporary password, and still knows it. If Baba gives Juma the pay
    # key now, Meneja could log in as Juma and hold a key the who-may rule kept from him (_check_may_set_password). So
    # while that password is open, a key its setter lacks waits: Juma chooses his own first, or the owner sets a new one
    # himself. Called with the person locked, so set_temporary_password can't slip in between.
    if not User.objects.filter(pk=staff.user_id, must_change_password=True).exists():
        return
    # Who set it is kept in the audit trail. The last line counts, as a later one replaced the password. No line, or
    # nobody named: typed in the admin, by the superuser, who reads every shop's rows anyway.
    set_by = (
        AuditEvent.objects.filter(
            action=AuditAction.STAFF_TEMPORARY_PASSWORD, subject_type=link_type_of(staff), subject_id=staff.pk
        )
        .order_by("-created_at", "-pk")
        .values_list("created_by_id", flat=True)
        .first()
    )
    if set_by is None:
        return
    # Only codes from the list, as _check_giver: a typo is reported as a typo, by the table's own rule.
    given = frozenset(code for code in codes if code in Permission.values)
    to_give = HeldPermissions(every_side=given) if side is None else HeldPermissions(on_side={side.pk: given})
    # What the setter holds now: one suspended since holds nothing, so they gain nothing through this person.
    if not held_permissions(StaffMember.objects.get(pk=set_by)).covers(to_give):
        raise ValidationError(
            "Who set this person's temporary password lacks this key: they choose their own first.",
            code="staff.temporary_password_open",
        )


def assign_role(staff: StaffMember, role: Role, *, side: Side | None, by: StaffMember | None) -> RoleAssignment:
    """Give a person a role on one side, or on every side (`side=None`), a side added later included. `by`: who
    gives it; None for the system or the superuser. Refused (staff.temporary_password_open) while a temporary password
    someone without those keys set is still open."""
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
        _check_no_open_temporary_password(staff, role.permissions, side)
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
        _check_no_open_temporary_password(staff, [permission], side)
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
    # repr=False: a dataclass prints every field by default, so a test's failure message, a log line or an error page
    # that printed this would show the key itself. Left out, it prints as NewPairing(request=...).
    key: str = field(repr=False)


# How many codes start_pairing draws before it gives up. A clash with a code already given is about 1 in a million
# even after a million asks, so a fifth clash in a row would mean a bug, not bad luck.
_CODE_DRAWS = 5


# Django's error reports, which a server with DEBUG off logs and sends, list each function's local variables when
# something fails (its debug page, with DEBUG on, shows everything). This marks `key` and `replacing`, the new key and
# the old, as ones to hide, here and in each function called from here that names them so (hash_device_key,
# NewPairing): they show as stars, never the device's secret.
@sensitive_variables("key", "replacing")
def start_pairing(*, replacing: str | None = None) -> NewPairing:
    """A new device asks to join a shop (03 §5.9, step 1). It gets a code to show and its key, which opens nothing
    until a manager confirms the code (confirm_pairing). Needs no shop open: the device belongs to no shop yet, and
    the request it waits in has none (02 v1.11).

    `replacing`: the key the device's cookie holds now, if any, as when it asks again with a double tap or after its
    code expired. A key that already opens a device is refused (pairing.already_paired): its new cookie would wipe a
    working key for good. A key still waiting has its code retired first, so a manager who types the old code gets
    pairing.code_expired, never a device whose key no browser holds (AUTH-2's review)."""
    # One transaction: the old code is retired only if the new one is made.
    with transaction.atomic():
        if replacing:
            _retire_waiting_key(hash_device_key(replacing))
        # The key is made here, by the device's own request, not when the manager confirms: confirming happens on the
        # manager's phone, which must never hold the device's key, and the server never keeps it in plain text, not
        # even until the device comes to collect it (Jack, AUTH-1).
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
                # Only a code already given (people_pairingrequest_code_once) is drawn again. Any other broken rule is
                # a bug in this code, and is raised as it is.
                if PairingRequest.objects.filter(code=request.code).exists():
                    continue
                raise
            return NewPairing(request=request, key=key)
        raise RuntimeError(f"No free pairing code after {_CODE_DRAWS} draws.")


def _retire_waiting_key(key_hash: str) -> None:
    # The request still waiting with this key, read and locked: the same lock confirm_pairing takes, so a manager
    # confirming its code at this very moment goes first, or after. If after, they find it expired. If first, the hash
    # has moved to the device by the time this read runs again (PostgreSQL checks a waited-for row once more), and the
    # door below finds that device.
    waiting = PairingRequest.objects.select_for_update().filter(key_hash=key_hash).first()
    if waiting is None:
        if shop_of_device_key(key_hash) is not None:
            # The key opens a device: confirmed earlier, or a moment ago. English for the logs; the app translates the
            # code (ADR-0032).
            raise ValidationError("This device is already paired.", code="pairing.already_paired")
        # A key nothing knows, made up or from a database that was reset: nothing to retire.
        return
    now = timezone.now()
    if waiting.expires_at > now:
        # Retired, not deleted (rule 7): its code stops working now, as if its 10 minutes were up.
        waiting.expires_at = now
        waiting.save(update_fields=["expires_at"])


def confirm_pairing(
    code: str, *, name: str, home_side: Side, by: StaffMember, device_id: uuid.UUID | None = None
) -> Device:
    """A manager says yes to a waiting device (03 §5.9, step 2): they type the code it shows, name it and pick its home
    side. The device is made in their own shop, active, with the shop's next device code and the key's hash, moved
    from the request, so its key works from now on. `by` is always a person, who needs device.manage on `home_side`.
    `device_id`: the id the manager's phone made for the new device (ADR-0007), if it made one. A confirm sent twice,
    by a double tap or after a lost answer, is refused here as pairing.code_used; the office route then finds the
    device the first one made by this id, and answers the repeat as a read (CreateOnceMixin, apps/core/api/base.py).
    Refusals: the code unknown, used or expired (pairing.code_unknown, .code_used, .code_expired); a name the shop
    already gives another device (device.name_taken)."""
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
        key_hash = request.key_hash
        if key_hash is None:
            # A bug, never a person's mistake: the database keeps a hash on every waiting request
            # (people_pairingrequest_key_only_while_waiting). Said loudly, never a device made with no key.
            raise RuntimeError(f"{request} waits with no key's hash.")
        device = Device(
            shop_id=by.shop_id,
            name=name,
            home_side=home_side,
            # D7: the shop's next device code. If anything below refuses, the transaction rolls back, and the number
            # with it: nothing kept it, so the next device gets it (apps/core/sequences.py).
            code=next_number(by.shop_id, SequenceName.DEVICE),
            key_hash=key_hash,
            created_by=by,
        )
        if device_id is not None:
            # The phone's id, not a new one, as add_side keeps a side's (apps/shops/services.py).
            device.id = device_id
        # Every field, clean() and the rules in Meta, before anything is written: a name the shop already uses comes
        # back as device.name_taken, and the code stays waiting for a better name.
        device.full_clean()
        device.save()
        request.device = device
        request.confirmed_at = now
        # The key's hash moves: from now on the device holds it and the request holds none (Jack, AUTH-2). One fact in
        # one place, and no way from a key through a request to a device of some shop, past the guard: the login finds
        # a key's shop through its one door (apps/people/login_doors.py). In this same transaction, so a refused
        # confirm leaves the hash on the waiting request, and the code can still be confirmed.
        request.key_hash = None
        request.save(update_fields=["device", "confirmed_at", "key_hash"])
    return device


def rename_device(device: Device, *, version: int, name: str, by: StaffMember) -> Device:
    """Give a device a new name on the shop's device list (UI-3), unless someone changed the device since `version`
    was read (02 §1): a rename screen opened before a block, or before another rename, is refused (VersionConflict,
    409) and loads the device again. Needs device.manage on the device's home side, as pairing and blocking it do.
    Refusals: a name the shop already gives another device (device.name_taken); no name, refused as Django's `blank`,
    or a name of spaces only, which full_clean trims to nothing (device.name_blank)."""
    # editing() checks the shop (T1), reads the device again and locks it, refuses a stale version, then checks the
    # new name (full_clean trims it, and the shop's one-name-per-device rule) and saves it with the next version.
    with editing(device, version=version, by=by) as fresh:
        # Who may: device.manage on the home side as stored, as block asks it (Jack, AUTH-1). Refused before anything
        # changes; the transaction leaves the device as it was.
        require(by, Permission.DEVICE_MANAGE, fresh.home_side)
        fresh.name = name
    return fresh


def block(device: Device, *, by: StaffMember, reason: str) -> Device:
    """Stop a device at once, perhaps stolen (03 §5.9, step 4): from its next request, its key opens nothing (AUTH-2).
    The key is kept, so unblock brings it back. Needs device.manage on the device's home side, and a reason."""
    return _set_device_status(
        device, DeviceStatus.ACTIVE, DeviceStatus.BLOCKED, AuditAction.DEVICE_BLOCK, by=by, reason=reason
    )


def unblock(device: Device, *, by: StaffMember, reason: str) -> Device:
    """Let a blocked device work again, with the same key, so the records it holds can still arrive (Jack, AUTH-1).
    Only for a device back in the shop's hands: a thief holding it could use it again. Checked as block is."""
    return _set_device_status(
        device, DeviceStatus.BLOCKED, DeviceStatus.ACTIVE, AuditAction.DEVICE_UNBLOCK, by=by, reason=reason
    )


# How fresh a device's `last_seen_at` is kept (02 v1.12): close enough for the device list and for spotting a stolen
# phone that still calls, and few enough writes that a busy counter laptop, calling many times a minute, writes about
# one every few minutes instead of one per request.
LAST_SEEN_EVERY = timedelta(minutes=5)


def note_device_seen(device: Device, *, at: datetime) -> bool:
    """Record that a device's key reached the server at `at`, unless the device was already seen less than
    LAST_SEEN_EVERY before. True when it was written: the login then sends the key's cookie again, so the browser
    keeps it (apps/people/api/base.py). Called by the login for every device it finds, a blocked one too."""
    _check_shop(device.shop_id, None)
    if device.last_seen_at is not None and at - device.last_seen_at < LAST_SEEN_EVERY:
        # Seen a moment ago, as the copy the login just read says: no query at all.
        return False
    # One UPDATE of this one column, not save() and not editing(): the row's version and `updated_at` stay as they
    # were, so a manager's rename screen, opened a minute ago, is never refused (409) because the device called. The
    # edit history skips the column (migration 0008). The time condition is in the UPDATE too: two requests of one
    # device at the same moment both pass the check above, and only the first writes. A single UPDATE is atomic on its
    # own, so it needs no transaction of ours.
    stale = Q(last_seen_at__isnull=True) | Q(last_seen_at__lte=at - LAST_SEEN_EVERY)
    written = Device.objects.filter(stale, pk=device.pk).update(last_seen_at=at)
    if written:
        device.last_seen_at = at
    return bool(written)


def _set_device_status(
    device: Device, was: DeviceStatus, becomes: DeviceStatus, action: AuditAction, *, by: StaffMember, reason: str
) -> Device:
    # block and unblock are one move each way: active → blocked, blocked → active.
    _check_shop(device.shop_id, by)
    _check_reason(reason, code="device.reason_required")
    with transaction.atomic():
        # The device as stored, read again and locked: its status and home side are checked as they are now, not as
        # the copy handed in says. Two managers blocking at once take turns, and the second finds it blocked.
        current = Device.objects.select_for_update().get(pk=device.pk)
        # Who may: device.manage on the home side as stored (Jack, AUTH-1), as for pairing it. Refused before anything
        # changes; the transaction leaves the device as it was.
        require(by, Permission.DEVICE_MANAGE, current.home_side)
        if current.status != was:
            code = "device.not_active" if was == DeviceStatus.ACTIVE else "device.not_blocked"
            raise ValidationError("The device is not in a state this action can change.", code=code)
        # Through editing(), as every office edit: the version moves on, `updated_by` names who, and the history's
        # trigger names the same person. With the version just read, never one a screen sent: a block is urgent, and
        # must not be refused because someone renamed the device a moment ago. A rename screen opened before the
        # block is the one refused (409), and loads the device again.
        with editing(current, version=current.version, by=by) as fresh:
            fresh.status = becomes
        # In the same transaction: if the line can't be written, the block is undone with it (T3).
        audit(action=action, subject=fresh, reason=reason, by=by, before={"status": was}, after={"status": becomes})
    return fresh
