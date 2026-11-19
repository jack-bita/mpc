"""apps/people/services.py — every write to the people tables, one function per action (ADR-0015).

A staff member's working life at one shop (02 §5): they are added, have their details fixed (change_worker, PPL-10),
are suspended, brought back and marked as left, hired again with a new job once they left (hire_again, PPL-11), and
given a PIN (set_pin; apps/people/pins.py hashes it) or a temporary password, face to face (set_temporary_password,
AUTH-6). A PIN login finds the person and checks their PIN, with its count of wrong tries (pin_login, check_pin,
AUTH-4). And what they may do there: a shop gets
its own copy of the role templates (copy_role_templates; set_up_shop makes a whole new shop with them),
and a person is given a role, or one extra permission, on one side or on all of them (assign_role,
grant_permission), by someone who may give it. And the shop's devices (AUTH-1, 03 §5.9): a new device asks to join
(start_pairing), a manager with device.manage says yes (confirm_pairing), renames it (rename_device, AUTH-5), and
blocks it, or lets it work again (block, unblock); and each time its key reaches the server, it is noted as seen
(note_device_seen, AUTH-2). What a laptop says about itself at each push is kept on its row and beside it: its unsent
count, app version and last sync (record_sync), and the offline periods it reports (record_outages); and its last
number, read and locked, then moved on, inside each pushed record's own transaction (lock_device_numbers,
move_device_number) (SYNC-5). And a person's own choices for their screens, their language and font, which only they
change (change_own_settings, UI-9). And the superuser's edit of a person in the admin, which every shop where they work
hears of when it touches what its laptops show: their name, language, or switch-off (change_person, SYNC-15).
Each action runs in one transaction, except five: note_device_seen, record_sync and move_device_number are one UPDATE
each, atomic on its own; record_outages is one INSERT; and lock_device_numbers locks inside its caller's transaction,
which it refuses to run without. Each checks that every row it links to belongs to the same shop (T1),
and refuses a broken rule with a ValidationError that carries a code (ADR-0032); CORE-6's error handler
will turn it into the API's error shape. A status change also writes its line in the audit trail, with
who and why, in the same transaction (apps/control/services.py, audit): the change and its line are kept
together or not at all (T3).

A shared laptop keeps a copy of the shop's people at work (apps/sync/registry.py): names, status, PIN time and keys,
all on their staff row. So each action that changes one of those saves inside `recording_changes(shop)`
(apps/core/changes.py), in place of a plain transaction, and names the person's job with record_change, last, after
every other write of the save: `archive` when they leave, as a laptop then drops them (SYNC-15). A role or an extra key
travels on the person's row, so giving one names the person. The refusals that need no transaction come first, so a
refused action opens nothing.

Callers open shop_context(shop) first: full_clean and the unique checks read through the guarded
`objects` (CORE-2). Four need none open: start_pairing, as a device that asks to join belongs to no shop yet, and its
request links to nothing (02 v1.11); set_up_shop, which opens the shop it makes itself; and change_own_settings and
change_person, which write the person, who belongs to no shop, and then open each shop where they work in turn, to
write that shop's line (_record_each_job).
"""

import math
import uuid
from collections.abc import Collection, Mapping, Sequence
from contextlib import nullcontext
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import cast

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q, QuerySet
from django.db.transaction import TransactionManagementError
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables

from apps.control.models import AuditAction, AuditEvent
from apps.control.services import audit
from apps.core.acting import acting_as
from apps.core.changes import record_change, recording_changes
from apps.core.editing import VersionConflict, editing
from apps.core.links import link_type_of
from apps.core.models import ChangeOp, SequenceName, ShopScoped
from apps.core.permissions import ROLE_TEMPLATES, HeldPermissions, Permission, RoleTemplate
from apps.core.phones import normalise_phone
from apps.core.sequences import next_number
from apps.core.tenancy import ALL_SHOPS, current_shop, shop_context
from apps.people.device_keys import (
    PAIRING_CODE_LIFETIME,
    clean_typed_code,
    hash_device_key,
    make_device_key,
    make_pairing_code,
)
from apps.people.login_counts import lift_wrong_password_count
from apps.people.login_doors import shop_of_device_key, shops_of_person
from apps.people.models import (
    OWN_SETTINGS,
    Device,
    DeviceOutage,
    DeviceStatus,
    PairingRequest,
    PermissionGrant,
    PinLock,
    Role,
    RoleAssignment,
    StaffMember,
    StaffStatus,
    User,
)
from apps.people.permissions import effective_permissions, given_permissions, held_permissions, require
from apps.people.pins import (
    FIRST_LOCK_MINUTES,
    LONGEST_LOCK_MINUTES,
    PIN_TRIES,
    check_pin_strength,
    hash_pin,
    pin_hash_is_old,
    pin_matches,
)
from apps.people.selectors import check_may_act
from apps.shops.models import Shop, ShopKind, Side
from apps.shops.selectors import shop_today
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


def add_staff(
    *,
    shop: Shop,
    user: User,
    display_name: str,
    job_title: str = "",
    started_on: date | None = None,
    staff_id: uuid.UUID | None = None,
    by: StaffMember | None,
) -> StaffMember:
    """Give a person a job at a shop. `staff_id`: the id the client made for the job (ADR-0007), if it made one. `by`:
    who adds them; None for the system or the superuser."""
    _check_shop(shop.pk, by)
    if started_on is None:
        started_on = shop_today(shop)
    staff = StaffMember(
        # The client's id when it sent one, so a send repeated finds the job the first one made (CreateOnceMixin).
        **({"id": staff_id} if staff_id is not None else {}),
        shop=shop,
        user=user,
        display_name=display_name,
        job_title=job_title,
        started_on=started_on,
        created_by=by,
    )
    with recording_changes(shop):
        # Every field, clean() and the rules in Meta, before anything is written: a clash comes back
        # as a code.
        staff.full_clean()
        try:
            # A savepoint of its own, so a refused save undoes only itself and the checks below can still read.
            with transaction.atomic():
                staff.save()
        except IntegrityError:
            # Two adds at the very same moment can both pass the check: Meneja adds Asha as "Asha" while Baba hires
            # the other Asha again as "Asha", each check blind to the other's save, not yet committed. The database's
            # unique rule waits for the first and refuses the second (PPL-11's review). Asked again, the checks now see
            # the first's save and answer with their code (staff.display_name_taken, staff.already_member), not a
            # server error. Anything they don't find, as an id another shop holds, is raised as it is, for the route
            # to read (CreateOnceMixin).
            staff.full_clean()
            raise
        record_change(staff)
    return staff


def add_worker(
    *,
    shop: Shop,
    full_name: str,
    display_name: str,
    job_title: str = "",
    started_on: date | None = None,
    phone: str | None = None,
    staff_id: uuid.UUID | None = None,
    by: StaffMember | None,
) -> StaffMember:
    """A new worker, as the owner adds one on the workers' page (PPL-4): the person and their job at this shop, in one
    step. Juma has never worked at any shop of this system, so he is a new person (User), with no password, as a worker
    logs in with a PIN (PPL-12). `phone`, typed as people write it, or None or "" for none (PPL-11): stored in one form,
    as every phone is. `staff_id`: the id the app made for the job (ADR-0007). `by`: who adds him, who needs
    staff.manage on the whole shop, as the route asks too; None for the system or the superuser. Refuses as add_staff
    does, a nickname another current worker has among them (staff.display_name_taken); a wrong phone (phone.invalid);
    the phone of a worker who left here, whom hire_again brings back instead (staff.left_here); and any other phone a
    person has (unique). It makes nothing then: the person and the job are kept together, or not at all."""
    _check_shop(shop.pk, by)
    if by is not None:
        # Asked again here, whatever calls this, not by the route alone (PPL-5).
        require(by, Permission.STAFF_MANAGE, None)
        # An empty box is no phone, which the demo allows.
        if phone:
            _check_phones_fixed_on_demo()
    # One block for both saves, which add_staff's own joins, so a refused job undoes the person too (SYNC-1).
    with recording_changes(shop):
        if phone:
            _check_phone_of_one_who_left(shop, phone)
        user = _new_person(full_name, phone or None)
        return add_staff(
            shop=shop,
            user=user,
            display_name=display_name,
            job_title=job_title,
            started_on=started_on,
            staff_id=staff_id,
            by=by,
        )


def _check_phone_of_one_who_left(shop: Shop, phone: str) -> None:
    # Baba starts adding Baraka as new, forgetting he worked here until 12 March, and types his phone. A second person
    # with Baraka's phone can't be made (it is unique), and shouldn't be: Baraka is one person. So the add makes
    # nothing, and the answer names his old job, so the page offers Mwajiri tena (hire_again). Only for a person whose
    # every job here ended, and who works nowhere now, whom hire_again would take: the same check, asked of the same
    # door (ADR-0045). For anyone else, the phone is only in use, which create_user says (unique): never by whom or
    # where, and never joined, as a manager of shop B who could join shop A's owner by his phone could then set his PIN
    # or a temporary password, and log in as him at shop A. Nothing locked: this only reads; the hire locks as it goes.
    try:
        typed = normalise_phone(phone)
    except ValidationError:
        # Not a phone: create_user says so beside the box (phone.invalid), with every other refusal of the add.
        return
    # The person's row is global, so this reads no shop's table; their jobs here are read through the guard, with the
    # shop named too, as under system_context() the guard shows every shop.
    person = User.objects.filter(phone=typed).first()
    if person is None:
        return
    here = list(StaffMember.objects.filter(shop_id=shop.pk, user_id=person.pk))
    if not here or any(job.status != StaffStatus.LEFT for job in here) or shops_of_person(person.pk):
        return
    # The job that ended last, whose page Mwajiri tena opens from. What the answer carries, the workers' list already
    # shows whoever may add: the full name and the last day, never the phone. A refusal of the whole add, as only that
    # carries its values in the API's answer (apps/core/api/errors.py); the page shows it under Simu.
    latest = max(here, key=lambda job: (cast(date, job.left_on), job.started_on))
    raise ValidationError(
        "This phone is of a worker who left.",
        code="staff.left_here",
        params={"staff": latest.pk, "full_name": person.full_name, "left_on": latest.left_on},
    )


def _new_person(full_name: str, phone: str | None) -> User:
    # A person, through create_user, which checks every field first, so a wrong phone and a blank name come back
    # together. A savepoint of its own, as a refused save must undo only itself: Meneja adds Juma with a new phone while
    # Baba adds Hamisi with the same one, in the same second. Each check passed, as neither saw the other's save, not
    # yet committed; the database's unique rule waits for the first and refuses the second. Asked again, the phone is
    # found, and the second hears it is in use (unique), as a fix does (change_worker), not a server error. Anything
    # else is another rule broken: a bug, raised as it is.
    try:
        with transaction.atomic():
            return User.objects.create_user(full_name=full_name, phone=phone)
    except IntegrityError:
        if phone is not None and User.objects.filter(phone=normalise_phone(phone)).exists():
            raise ValidationError(
                {"phone": ValidationError("A person with this phone exists.", code="unique")}
            ) from None
        raise


def hire_again(
    old: StaffMember,
    *,
    display_name: str,
    job_title: str = "",
    started_on: date | None = None,
    staff_id: uuid.UUID | None = None,
    by: StaffMember | None,
) -> StaffMember:
    """A worker who left, hired again as the same person (PPL-11, 02 §5): a new job at this shop for the person of
    `old`, a job here that ended. Baraka left on 12 March and Baba hires him again in June: one person still, so his
    phone and his password stay his, and his new job starts on `started_on` (today if None), with the nickname and job
    title typed for it. The old job keeps what it said, and its history with it. `staff_id`: the id the app made for the
    new job (ADR-0007). `by`: who hires him, who needs staff.manage on the whole shop, as for an add: he comes back with
    no role, no extra key and no PIN, so hiring him gives nobody anything over him; None for the system or the
    superuser. Refuses a job that hasn't ended (staff.not_left), a person back already (staff.already_member), one who
    works at another shop now (staff.works_elsewhere), a first day before his latest last day (staff.back_before_left),
    and, as add_staff does, a nickname another current worker holds (staff.display_name_taken)."""
    _check_shop(old.shop_id, by)
    if by is not None:
        # Asked again here, whatever calls this, not by the route alone (PPL-5).
        require(by, Permission.STAFF_MANAGE, None)
    shop = old.shop
    if started_on is None:
        started_on = shop_today(shop)
    # One block for the checks and the save, which add_staff's own joins: the new job is written on what the checks saw.
    with recording_changes(shop):
        # The person's row locked first, lightly (no key: the new job's link to them only reads it), and every check
        # read after it. Meneja and Baba tap Mwajiri tena on Baraka in the same second: the second waits here until the
        # first is done, then finds him back already (staff.already_member), not a server error from the database's
        # rule (people_staffmember_one_current_job), which a check run before the first commit could not see. No job is
        # locked for a change: the new job's link to the one acting takes only the lightest lock on that job (KEY
        # SHARE), which change_worker's lock of it (no key) never waits for, so this never waits in a circle with
        # change_worker, which locks the jobs before the person.
        person = User.objects.select_for_update(no_key=True).get(pk=old.user_id)
        # His jobs here, read through the guard, with the shop named too: under system_context() the guard shows every
        # shop, and another shop's job must not count as one here.
        here = list(StaffMember.objects.filter(shop_id=shop.pk, user_id=person.pk))
        if next(job for job in here if job.pk == old.pk).status != StaffStatus.LEFT:
            raise ValidationError("This job hasn't ended.", code="staff.not_left")
        if any(job.status != StaffStatus.LEFT for job in here):
            raise ValidationError("This person works here already.", code="staff.already_member")
        # A current job at another shop, found through the person's door, which reads shops' ids alone (ADR-0045): a
        # job here too would make him a person at two shops before AUTH-7, whose login AUTH-3 refuses, and this shop
        # could then fix the name and phone the other shows (ADR-0044). Only counted; the refusal names no shop.
        if any(shop_id != shop.pk for shop_id in shops_of_person(person.pk)):
            raise ValidationError("This person works at another shop.", code="staff.works_elsewhere")
        # Never before his latest last day here, of every job that ended: two jobs on the same days would count and pay
        # those days twice. The same day may: a leaving marked by mistake is mended at once (default).
        last_day = max(cast(date, job.left_on) for job in here)
        if started_on < last_day:
            raise ValidationError(
                {"started_on": ValidationError("The first day is before the last one.", code="staff.back_before_left")}
            )
        return add_staff(
            shop=shop,
            user=person,
            display_name=display_name,
            job_title=job_title,
            started_on=started_on,
            staff_id=staff_id,
            by=by,
        )


def _check_reason(reason: str, *, code: str = "staff.reason_required") -> None:
    # Rule 7: a suspension, a leaving or a device's block is always recorded with who, when and why. Checked
    # before anything is locked; audit() keeps the reason, trimmed, in the action's own line (CTRL-2). `code`
    # names what needs the reason, so the screen says it in its own words (ADR-0032).
    if not reason.strip():
        raise ValidationError("A reason is required.", code=code)


def _save(staff: StaffMember, *, by: StaffMember | None, fields: list[str]) -> None:
    # Saves the changed fields, with `by` told to PostgreSQL for the save: the history line its trigger writes then
    # names the same person as the action's audit line, even outside an office visit, as in a job or a command
    # (02 v1.7: one fact, one answer; apps/core/acting.py). With `by` None, the system acts, and nobody is told. No
    # device named here: the visit's stays as told (X3).
    with acting_as(by) if by is not None else nullcontext():
        staff.save(update_fields=fields)


def _locked(staff: StaffMember) -> StaffMember:
    # The row read again, and locked until the transaction ends (SELECT ... FOR NO KEY UPDATE). Two managers
    # acting on Asha at the same moment take turns, and the second sees what the first one wrote, not
    # the old copy on their screen. no_key, as in _locked_pair: a line that only links to this person, such as an audit
    # line naming them as who acted, doesn't wait, or two managers acting on each other would deadlock.
    return StaffMember.objects.select_for_update(no_key=True).get(pk=staff.pk)


def _locked_for_a_change(staff: StaffMember, by: StaffMember | None) -> tuple[StaffMember, StaffMember | None]:
    # A person's job changed by someone at the shop, its status or their details (PPL-10): both jobs locked, then who
    # may asked (PPL-4, AUTH-8). The order is the point. Asked before the lock, the answer could be out of date by the
    # time the change is written: Neema and Hamisi suspend each other in the same second, each check sees the other
    # still active, and both go through. Asked after, on the rows as they are now, the second waits until the first is
    # done and then finds the one it acts as suspended, holding nothing: refused (PermissionDenied), so the first wins.
    # _locked_pair takes both rows in id order, so two such changes never wait for each other in a circle. `by` None:
    # the system, or the superuser, who may change anyone, the owner included; only the person's own row is locked, as
    # before. Returns both rows as read under the locks, so the change writes the person as they are now, and names the
    # one acting as they are.
    if by is None:
        return _locked(staff), None
    _check_people_fixed_on_demo(staff)
    staff, by = _locked_pair(staff, by)
    # The person's own row (User), read afresh, not locked: who may hangs on the jobs, locked above, and on whether the
    # person can open the admin, which no shop's screen changes.
    _check_may_act_as(staff, User.objects.get(pk=staff.user_id), by=by, what="staff")
    return staff, by


def lock_worker_for_a_change(staff: StaffMember, by: StaffMember | None) -> tuple[StaffMember, StaffMember | None]:
    """The PIN's rule (02 §5), for a change another app makes to a worker, as setting their pay rate (WAGE-1): the
    same lock and the same check as a suspension or a fix of their details, never a copy of them. Checks that both
    jobs are of the shop open (T1), locks both, then asks who may on them as they are now; returns both as read under
    the locks. `by` None: the system or the superuser, who may change anyone. Call it inside the transaction that writes
    the change, so the locks hold until it commits. Refuses with the codes of a change to a worker (`staff.own`,
    `staff.superuser_only`, `staff.more_keys`, `staff.left`; on the demo, `demo.people_fixed`), and 403 without
    `staff.manage` on the whole shop."""
    # Another app's door to the lock above: the people app owns who may change a worker, so a second copy of the rule
    # elsewhere could drift from it. The shop check is the one each of this file's own services makes first.
    _check_shop(staff.shop_id, by)
    return _locked_for_a_change(staff, by)


def _check_people_fixed_on_demo(staff: StaffMember) -> None:
    # On the demo every visitor logs in as Meneja (OPS-3), who holds staff.manage there, so a visitor can try the
    # workers' page (Jack, PPL-4: A). The people the seed made stay as made: a visitor who suspended Asha, or marked
    # Baraka left, would take them off every other visitor's PIN tiles until the next morning's seed; and Meneja is
    # one of them, so his own login, the only one visitors have, is refused here, before staff.own is asked. A worker
    # a visitor added can be changed, as trying that is the point. The seed's people are those the system made, with
    # no one named as their adder: the seed passes no `by`, while a visitor's add names Meneja (add_worker). Only for a
    # person acting: the system, which is how the seed works, still may. Read from the demo's sign, as
    # check_logins_may_change does, before anything is locked or written.
    if settings.DEMO_SEED and staff.created_by_id is None:
        raise ValidationError("On the demo, the people the seed made stay as they are.", code="demo.people_fixed")


def suspend(staff: StaffMember, *, by: StaffMember | None, reason: str) -> StaffMember:
    """Stop an active person working for a while. Their PIN stops working (AUTH-4). `by`: who suspends them, who needs
    staff.manage on the whole shop and every key the person holds, and is never the person, nor an owner's or an admin
    person's (_locked_for_a_change); None for the system or the superuser."""
    _check_shop(staff.shop_id, by)
    _check_reason(reason)
    with recording_changes(staff.shop_id):
        staff, by = _locked_for_a_change(staff, by)
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
        # Laptops must hear of it: offline, a suspended person's PIN is refused there too (X2).
        record_change(staff)
    return staff


def unsuspend(staff: StaffMember, *, by: StaffMember | None, reason: str) -> StaffMember:
    """Let a suspended person work again. Who may: as for suspend; bringing someone back hands them every key they hold
    again, so the one acting must hold those keys too."""
    _check_shop(staff.shop_id, by)
    _check_reason(reason)
    with recording_changes(staff.shop_id):
        staff, by = _locked_for_a_change(staff, by)
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
        record_change(staff)
    return staff


def mark_left(staff: StaffMember, *, left_on: date, by: StaffMember | None, reason: str) -> StaffMember:
    """Record that a person left on `left_on`. Final: if they come back, hire_again gives them a new job. Who may: as
    for suspend."""
    _check_shop(staff.shop_id, by)
    _check_reason(reason)
    # On their last day or after, never ahead (Jack, 27 Oct): `left` takes effect at once, so "leaves on
    # Friday" typed on Monday would stop their PIN four days early.
    if left_on > shop_today(staff.shop):
        raise ValidationError("A leaving date can't be in the future.", code="staff.left_in_future")
    with recording_changes(staff.shop_id):
        staff, by = _locked_for_a_change(staff, by)
        # Asked of a person at the shop by _locked_for_a_change already; here for the system's own change.
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
        # Archive: a person who left is no longer sent, and every laptop drops them from its PIN screen.
        record_change(staff, ChangeOp.ARCHIVE)
    return staff


# What a fix may change on a worker's page (PPL-10): the person's own details, which follow them to every shop where
# they work (D12), and their job's, which are this shop's alone.
PERSON_DETAILS = ("full_name", "phone")
JOB_DETAILS = ("display_name", "job_title", "started_on")


def change_worker(
    staff: StaffMember,
    *,
    version: int,
    reason: str,
    by: StaffMember | None,
    full_name: str | None = None,
    phone: str | None = None,
    display_name: str | None = None,
    job_title: str | None = None,
    started_on: date | None = None,
) -> StaffMember:
    """Fix a worker's details, typed wrong when they were added, or changed since: their full name and phone, which are
    the person's (User), and their nickname, job title and first day, which are their job's here (02 §5). A detail left
    None stays as it is: the page sends only the boxes it changed. `phone` "" takes the phone off. `version`: the job's
    version the page read; an older one is refused (VersionConflict, 409 version_conflict), as someone fixed the worker
    since. `by`: who fixes them, under the PIN's rule (_locked_for_a_change); None for the system or the superuser.
    `reason` is required, and kept in the fix's audit line with each changed detail, before and after. Returns the job
    as saved, its person read with it."""
    _check_shop(staff.shop_id, by)
    _check_reason(reason)
    if phone is not None and by is not None:
        _check_phones_fixed_on_demo()
    # Spaces around a name say nothing, and "  " is no name: trimmed here, so a blank one is refused as blank. The
    # nickname's own clean() trims it too; the phone's field cleans what was typed into one stored form.
    sent_person = {"full_name": _trimmed(full_name), "phone": phone}
    sent_job = {"display_name": _trimmed(display_name), "job_title": _trimmed(job_title), "started_on": started_on}
    # One transaction for the job, the person, the audit line and every shop's line: all, or none. Not a block of one
    # shop: a new full name writes a line in each shop where the person works, each in a block of its own, one after
    # another, never one inside another (SYNC-15), as change_own_settings does.
    with transaction.atomic():
        # Both jobs locked, then who may asked on them as they are now (the PIN's rule, 02 §5): a manager handed
        # staff.manage can fix his workers, never himself, never the owner, nor anyone holding a key he lacks.
        staff, by = _locked_for_a_change(staff, by)
        # Asked of a person at the shop by _locked_for_a_change already; here for the system's own fix too. A job that
        # ended is history: what it said then stays as it was.
        if staff.status == StaffStatus.LEFT:
            raise ValidationError("This person has already left.", code="staff.left")
        # A stale copy is refused before its boxes are judged: whatever they hold, they were typed on an old copy, and
        # the page reads the worker again. editing() asks this again below, under the same lock.
        if staff.version != version:
            raise VersionConflict()
        # The person locked too, lightly (no key), after the jobs: two managers of two shops fixing one person's name
        # at once take turns, and each line's "before" is true. A new phone takes the full lock as it saves, as
        # PostgreSQL counts a plain unique column as part of the row's key (AUTH-8). Locks still follow it: the audit
        # line's light ones, and, for a new name or nickname, the shops' change counters. No circle can form: every
        # service that writes a person and then counters takes the person first (change_own_settings, change_person),
        # and none holds a shop's counter while it waits for a person.
        user = User.objects.select_for_update(no_key=True).get(pk=staff.user_id)
        was = {name: getattr(user, name) for name in PERSON_DETAILS} | {
            name: getattr(staff, name) for name in JOB_DETAILS
        }
        # Every box sent, checked before anything is written, and every refusal together, each under its own box: a
        # wrong phone and an empty nickname are both said at once.
        _check_details(user, staff, sent_person, sent_job)
        _check_a_login_name_is_left(user, had_phone=was["phone"] is not None)
        changed = [name for name in (*PERSON_DETAILS, *JOB_DETAILS) if _now(user, staff, name) != was[name]]
        if not changed:
            # Nothing to fix: no new version, no audit line, no line for the laptops. The page sends only what changed,
            # so this is a box typed back as it was.
            return staff
        # The job, through editing(): it reads the job again under the lock already held, refuses a stale version
        # once more, checks every rule (full_clean), and moves the version on, naming who fixed it. Moved even when
        # only the person's details changed: the page's copy holds them too, so a second fix of Asha's phone, typed on
        # the copy read before the first, is refused like any other.
        try:
            with editing(staff, version=version, by=by) as fresh:
                for name in JOB_DETAILS:
                    setattr(fresh, name, getattr(staff, name))
            person_changed = [name for name in PERSON_DETAILS if name in changed]
            if person_changed:
                # A savepoint of its own, as editing() has: a refused save undoes only itself, and the checks below can
                # still read.
                with transaction.atomic():
                    user.save(update_fields=person_changed)
        except IntegrityError:
            # Meneja names Asha "Juma" while Baba names Neema "Juma", in the same second: each check above passed, as
            # neither saw the other's save, not yet committed; the database's unique rule waits for the first and
            # refuses the second (people_staffmember_nickname_unique; a phone's, likewise). The checks, asked again,
            # now see the first's save and answer with their code beside the box, not a server error. Anything they
            # don't find is another rule broken: a bug, raised as it is.
            _check_details(user, staff, sent_person, sent_job)
            raise
        fresh.user = user
        # The person's details have no edit history (ADR-0036): User belongs to no shop. So the audit line keeps all of
        # them, the job's beside them, with who and why: Baba sees who changed Asha's phone, and why, in one line.
        audit(
            action=AuditAction.STAFF_DETAILS_CHANGED,
            subject=fresh,
            reason=reason,
            by=by,
            before={name: was[name] for name in changed},
            after={name: _now(user, fresh, name) for name in changed},
        )
        # What a laptop shows travels on the staff row: the full name in every shop where the person works, this one
        # included (_record_each_job); the nickname, here. The job title, the first day and the phone never leave the
        # server, so they tell no laptop anything.
        if "full_name" in changed:
            _record_each_job(user)
        elif "display_name" in changed:
            with recording_changes(fresh.shop_id):
                record_change(fresh)
    return fresh


def _trimmed(value: str | None) -> str | None:
    return None if value is None else value.strip()


def _now(user: User, staff: StaffMember, name: str) -> object:
    # A detail as it stands now: the person's on the person, the job's on the job.
    return getattr(user if name in PERSON_DETAILS else staff, name)


def _check_details(
    user: User, staff: StaffMember, sent_person: Mapping[str, str | None], sent_job: Mapping[str, object]
) -> None:
    # Each sent detail set on the rows in hand, never saved here, and checked by the rules every form keeps
    # (full_clean): a blank name (blank), a wrong phone (phone.invalid), a phone another person has (unique, which says
    # only that it is in use, never by whom or at which shop), a nickname a current worker holds
    # (staff.display_name_taken). Only the person's sent details are judged: the rest of the person isn't this fix's
    # to judge, as in change_own_settings. The job is judged whole, as editing() will judge it. Every refusal together.
    for name, value in (*sent_person.items(), *sent_job.items()):
        if value is not None:
            setattr(user if name in PERSON_DETAILS else staff, name, value)
    refused: dict[str, list[ValidationError]] = {}
    person_sent = {name for name, value in sent_person.items() if value is not None}
    not_sent = [column.name for column in User._meta.concrete_fields if column.name not in person_sent]
    for row, exclude in ((user, not_sent), (staff, None)):
        try:
            row.full_clean(exclude=exclude)
        except ValidationError as error:
            for name, errors in error.error_dict.items():
                refused.setdefault(name, []).extend(errors)
    if refused:
        raise ValidationError(refused)


def _check_a_login_name_is_left(user: User, *, had_phone: bool) -> None:
    # A login is by phone or by email (AUTH-3). Baba set Asha a temporary password, and she has no email: her phone is
    # her only way in. Meneja empties her Simu box, and she could never log in again, her temporary password's mark on
    # for good, which password.no_login_name exists to prevent (_check_may_set_password). So the phone of someone with a
    # password and no email may change, as she then logs in with the new number and the same password, but never go.
    # A worker who logs in with a PIN alone has no password to lose (create_user leaves it unusable): theirs may go.
    if had_phone and user.phone is None and user.has_usable_password() and not user.email:
        raise ValidationError(
            {"phone": ValidationError("This person logs in with this phone.", code="phone.needed_to_log_in")}
        )


def _check_phones_fixed_on_demo() -> None:
    # On the demo every visitor logs in as Meneja (OPS-3), so a stranger could type a real person's phone on a worker
    # they added, for every later visitor to read on the workers' page until the next morning's seed. And a phone serves
    # no login there: the logins stay as they are (check_logins_may_change). So no worker gets one (Jack, PPL-10: A);
    # their other details can be fixed. Only for a person acting: the system still may.
    if settings.DEMO_SEED:
        raise ValidationError("On the demo, workers get no phone.", code="demo.phones_fixed")


def check_logins_may_change() -> None:
    """Refuse any change to a password or a PIN on the demo (Jack, 8 Nov 2026). Its logins are public, so every visitor
    shares them: a visitor who changed the manager's password would lock out everyone after them, and without the
    manager nobody can confirm a laptop, until the next day's seed (apps/demo/services.py). Read from the demo's sign,
    DEMO_SEED (config/settings/base.py), not from a shop's kind: the sign is set only where demo shops are the only
    shops (the seed refuses any other), and the own-password form has no shop open to read a kind from. The system
    still sets them: the seed passes no `by`."""
    if settings.DEMO_SEED:
        raise ValidationError(
            "On the demo, passwords and PINs stay as they are, so every visitor can log in.", code="demo.logins_fixed"
        )


# Every variable shows as stars in Django's error reports, here and in everything this calls: `pin` is the PIN itself.
@sensitive_variables()
def set_pin(staff: StaffMember, pin: str, *, by: StaffMember | None) -> StaffMember:
    """Give a person a new PIN, online only (03 §5.9). Devices see the new `pin_changed_at` at their next
    sync and drop their old offline check. A PIN logs in as the whole person, so who may is the rule for a password,
    with codes of its own (_check_may_act_as; Jack, 4 Nov 2026). `by` None: the system, or the superuser, who is
    nobody's staff, and the only one who sets an owner's. On the demo, only the system may (check_logins_may_change)."""
    _check_shop(staff.shop_id, by)
    # A person never changes a PIN on the demo, where visitors share the seed's; the seed itself passes no `by`.
    if by is not None:
        check_logins_may_change()
    # Who may, first, before anything else: a refused try pays for no slow hash. Asked again under the locks below, as
    # this copy can be out of date by then.
    if by is not None:
        _check_may_act_as(staff, staff.user, by=by, what="pin")
    check_pin_strength(pin)
    # Hashed before the lock: Argon2 is slow on purpose, and the row stays locked only for the short
    # write below.
    pin_hash = hash_pin(pin)
    with recording_changes(staff.shop_id):
        if by is None:
            staff = _locked(staff)
        else:
            staff, by = _locked_pair(staff, by)
            _check_may_act_as(staff, User.objects.get(pk=staff.user_id), by=by, what="pin")
        if staff.status == StaffStatus.LEFT:
            raise ValidationError("A person who has left can't be given a PIN.", code="staff.left")
        staff.pin_hash = pin_hash
        staff.pin_changed_at = timezone.now()
        staff.full_clean()
        _save(staff, by=by, fields=["pin_hash", "pin_changed_at"])
        # A new PIN ends any lock at once, on every device: a worker locked out by a coworker's wrong tries asks a
        # manager, and needs no waiting (Jack, 4 Nov 2026).
        _lift_pin_locks(PinLock.objects.filter(staff=staff))
        # The new `pin_changed_at` travels, never the hash: each laptop drops its offline check of the old PIN.
        record_change(staff)
    return staff


def _pin_locked(lock: PinLock, at: datetime) -> ValidationError:
    # `wait`: whole seconds, rounded up, so the app never says "try again in 0 seconds" (ADR-0032). `locked_until` is
    # never empty here: each caller has just read or set it.
    wait = math.ceil((cast(datetime, lock.locked_until) - at).total_seconds())
    return ValidationError("This person is locked on this device.", code="pin.locked", params={"wait": wait})


def _count_pin_try(staff: StaffMember, device: Device, *, at: datetime) -> PinLock:
    # Counted before the PIN is checked, holding the row's lock, and kept even if the check then crashes. Checked first,
    # twelve tries sent at once would each read "no wrong tries yet", and all twelve would get through. The lock is
    # dropped before the slow check, so a person's other tries wait for no hash.
    with transaction.atomic():
        lock, _ = PinLock.objects.select_for_update().get_or_create(
            staff=staff, device=device, defaults={"shop_id": staff.shop_id}
        )
        if lock.locked_until is not None and at < lock.locked_until:
            raise _pin_locked(lock, at)
        lock.wrong_tries += 1
        if lock.wrong_tries == PIN_TRIES:
            lock.wrong_tries = 0
            lock.locked_until = at + timedelta(minutes=lock.next_lock_minutes)
            lock.next_lock_minutes = min(lock.next_lock_minutes * 2, LONGEST_LOCK_MINUTES)
        lock.save(update_fields=["wrong_tries", "next_lock_minutes", "locked_until"])
    return lock


def _lift_pin_locks(rows: QuerySet[PinLock]) -> None:
    rows.update(wrong_tries=0, next_lock_minutes=FIRST_LOCK_MINUTES, locked_until=None)


# Every variable shows as stars in Django's error reports, here and in everything this calls: `pin` is the PIN itself.
@sensitive_variables()
def check_pin(staff: StaffMember, device: Device, pin: str, *, at: datetime) -> None:
    """Is this the person's PIN, on this device, at this moment? Answers by returning; refuses with pin.wrong, or
    pin.locked and the seconds to wait (03 §5.9)."""
    # T1, both halves: the shop open is theirs, and the person and the device belong together. Without the first, a
    # visit of shop A could write a count into shop B's rows, which its next read wouldn't find.
    _check_shop(staff.shop_id, None)
    _check_same_shop(staff, device)
    lock = _count_pin_try(staff, device, at=at)
    if pin_matches(pin, staff.pin_hash, staff_id=staff.pk):
        _lift_pin_locks(PinLock.objects.filter(pk=lock.pk))
        return
    # The fifth wrong try has just started a lock: say so now, so the screen can tell her how long.
    if lock.locked_until is not None and at < lock.locked_until:
        raise _pin_locked(lock, at)
    raise ValidationError("This PIN is wrong.", code="pin.wrong")


def _move_pin_to_todays_cost(staff: StaffMember, pin: str) -> None:
    # One UPDATE of this one column. `pin_changed_at` stays: her PIN didn't change, so devices keep their offline check
    # of it (03 §5.9). The history skips the hash (ADR-0036), so the owner's trail says nothing. Only if the hash is
    # still the one just checked: a new PIN set at this same moment must not be overwritten with the old one.
    StaffMember.objects.filter(pk=staff.pk, pin_hash=staff.pin_hash).update(pin_hash=hash_pin(pin))


# Every variable shows as stars in Django's error reports, here and in everything this calls: `pin` is the PIN itself.
@sensitive_variables()
def pin_login(device: Device, staff_id: uuid.UUID, pin: str, *, at: datetime) -> StaffMember:
    """The person this PIN logs in, on this device (03 §5.9). Refuses with pin.wrong or pin.locked, or LoginRefused for
    someone who can't act today."""
    _check_shop(device.shop_id, None)
    # Read through the guard, inside the device's shop: another shop's person isn't found (X2, T1).
    staff = (
        StaffMember.objects.select_related("shop", "user").filter(pk=staff_id).exclude(status=StaffStatus.LEFT).first()
    )
    if staff is None or not staff.user.is_active:
        # Nobody here by that id: another shop's person, someone who left or was switched off, or a made-up id. The same
        # answer as a wrong PIN, after the same work, so neither the words nor the time tell them apart.
        pin_matches(pin, "")
        raise ValidationError("This PIN is wrong.", code="pin.wrong")
    # Before the PIN: this costs no memory, and a suspended person's wrong tries don't lock them for later.
    check_may_act(staff)
    check_pin(staff, device, pin, at=at)
    if pin_hash_is_old(staff.pin_hash):
        _move_pin_to_todays_cost(staff, pin)
    return staff


# Every variable shows as stars in Django's error reports, which list each function's variables when something fails,
# here and in everything this calls. Hiding `password` by its name wouldn't do: the library at the bottom of the hash
# names it `secret`, and running out of memory there is the likeliest crash on the demo's 512 MB. A crash here shows its
# lines, only not its values.
@sensitive_variables()
def set_temporary_password(staff: StaffMember, password: str, *, by: StaffMember, reason: str) -> None:
    """Set a first or forgotten password, face to face (ADR-0038): Baba types one for Asha and tells it to her. She logs
    in with it, and every office route but `me` refuses her until she chooses her own (apps/people/selectors.py). `by`
    is always a person, who needs staff.manage on the whole shop, as a password opens the whole person. Refusals, each a
    code the screen translates: the password's checks, under `password`; staff.reason_required; staff.left; who may
    (_check_may_set_password); and demo.logins_fixed on the demo, whose logins visitors share (check_logins_may_change).
    Her older logins end, as each holds a fingerprint of the password it started with, so a lost phone is logged out.
    Returns nothing: the password goes no further than this function (no answer, log or audit line holds it)."""
    _check_shop(staff.shop_id, by)
    # Never on the demo, before anything else: a temporary password would lock its visitors out of a shared login.
    check_logins_may_change()
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
        staff, by = _locked_pair(staff, by)
        # Her person, read afresh. Not locked: everything that decides who may hangs on the jobs locked above, and the
        # write below names only its own two columns.
        user = User.objects.get(pk=staff.user_id)
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
        # Her count of wrong passwords, a row of the cache's table in the same database, so in the same transaction: if
        # this fails, the owner is told it failed, and it did. All or nothing, and no password set behind an error.
        lift_wrong_password_count(user)


def _locked_pair(staff: StaffMember, by: StaffMember) -> tuple[StaffMember, StaffMember]:
    # A person's job and the job of the one acting, read again and locked. A role given to them, a leaving recorded, or
    # a suspension of the one acting, at this same moment, comes first and is seen here, or waits until this is done:
    # the slow hash before it left plenty of time for one. In id order, so two people each setting the other's password
    # at once take turns. no_key: a row another transaction links to needs a light lock at that transaction's commit,
    # and a full lock here would block it, while this waits for that same transaction: Baba giving Juma a key while
    # setting his password would deadlock, and one request would answer a server error.
    rows = StaffMember.objects.select_for_update(no_key=True).filter(pk__in=[staff.pk, by.pk]).order_by("pk")
    jobs = {job.pk: job for job in rows}
    return jobs[staff.pk], jobs[by.pk]


def _check_may_set_password(staff: StaffMember, user: User, *, by: StaffMember) -> None:
    _check_may_act_as(staff, user, by=by, what="password")
    # A login is by phone or by email. With neither, the password could never be used, and the mark would stay on for
    # good: the owner is told now, and adds the phone first, not when the person can't log in.
    if not user.phone and not user.email:
        raise ValidationError("This person has no phone or email to log in with.", code="password.no_login_name")


def _check_may_act_as(staff: StaffMember, user: User, *, by: StaffMember, what: str) -> None:
    # Whoever sets a person's password or PIN can log in as them; whoever suspends them, brings them back or marks them
    # left decides whether they work at all; whoever fixes their phone sets their login name (PPL-10). So this is the
    # giver rule (02 §5), for a whole person: Baba may hand a manager staff.manage to deal with a forgotten password, or
    # a worker who stopped coming, and that manager still can't become, or stop, anyone stronger than himself (Jack,
    # 4 Nov 2026; PPL-4). `what` names the refusal's codes: "password", "pin", or "staff" for a change of status or of
    # their details. Refused as a ValidationError with its code, as flag.own_flag is, so the screen can say what to do.
    # The English words are for the logs: neutral, as they serve all three; the screens translate the code (ADR-0032).
    # The key, on the whole shop, read afresh: a giver suspended a moment ago holds nothing (PermissionDenied, 403).
    require(by, Permission.STAFF_MANAGE, None)
    if staff.status == StaffStatus.LEFT:
        raise ValidationError("This person has left.", code="staff.left")
    if staff.pk == by.pk:
        # A thief holding a logged-in phone could set a new one for its owner, with no current one, and keep the login
        # for good. A person changes their own password by allauth's change route, which asks for the current one. A PIN
        # has no such route: someone else sets it, face to face, and the worker types it on their phone (PPL-12). And
        # a manager who suspended himself, or marked himself left, would lock himself out by a slip of the finger.
        raise ValidationError("A person doesn't do this to themselves here.", code=f"{what}.own")
    # The superuser's alone (ADR-0038). Read from the roles, whatever the person's status: a suspended owner holds no
    # keys but is still the owner, and two owners may have fallen out with each other. An Owner role taken away (PPL-7)
    # no longer counts: they are then a worker like any other.
    is_owner = RoleAssignment.objects.filter(
        staff=staff, role__template=RoleTemplate.OWNER, ended_at__isnull=True
    ).exists()
    # Someone who can open the admin reads every shop's rows, so they stand above any shop's people: no shop's owner may
    # act as them, whether by their password, which opens the admin, or by their PIN, which opens their job. A job at
    # another shop isn't looked at: reading that shop's rows during this shop's visit, to decide who may, would pass the
    # guard, which no door is for: a door finds a login's shop, or the shops a change to a person must reach, and reads
    # their ids alone (ADR-0042, which supersedes ADR-0037; Jack, 4 Nov 2026). Nothing is lost yet, as a person at two
    # shops is refused at every office route until AUTH-7, whose card adds this rule.
    if is_owner or user.is_superuser or user.is_staff:
        raise ValidationError("Only the superuser may do this for this person.", code=f"{what}.superuser_only")
    # What the person was given, whatever their status, as they hold it all again once brought back; against what the
    # one acting holds now.
    if not held_permissions(by).covers(given_permissions(staff)):
        raise ValidationError("This person holds a key the one acting doesn't.", code=f"{what}.more_keys")


def change_own_settings(user: User, *, language: str | None = None, font: str | None = None) -> User:
    """A person changes their own language or font, or both (UI-9, ADR-0039): the screens then follow them to every
    device they log in at. Only the person: `user` is whoever is logged in, never a person named in a request, so nobody
    changes another's. The route has already refused anyone who may not act today (a suspension, a temporary password),
    through the login every office route shares. A choice left None stays as it is: the screen sends only the one just
    tapped. Refuses an unknown value under its field, with its code (invalid_choice); the database's rules are the last
    guard (people_user_language_known, people_user_font_known). Returns the person as saved."""
    sent = {"language": language, "font": font}
    changed = [name for name in OWN_SETTINGS if sent[name] is not None]
    # Each changed field's own checks, its list of choices above all, and nothing else of the row: the rest of the
    # person isn't this action's to judge. Checked before anything is set, so a refusal leaves the person in hand as
    # saved, the good half of a change included (UI-9's review).
    columns = {column.name: column for column in User._meta.concrete_fields}
    refused: dict[str, list[ValidationError]] = {}
    for name in changed:
        try:
            columns[name].clean(sent[name], user)
        except ValidationError as error:
            refused[name] = error.error_list
    if refused:
        raise ValidationError(refused)
    for name in changed:
        setattr(user, name, sent[name])
    if changed:
        # Only the changed columns: a change to her font in one tab never writes back an old language from another. No
        # lock and no version: each choice is one value, and the last one tapped is the one she meant. No line in the
        # audit trail either: it keeps who changed what in a shop, and this changes no shop's rows, nobody's rights and
        # no money, only how one person's own screens look. One transaction with every shop's line: all, or none.
        with transaction.atomic():
            user.save(update_fields=changed)
            _record_each_job(user)
    return user


# What a laptop shows of a person, on their staff row in each shop where they work (StaffRecord, apps/sync/api/
# serializers.py): their name, language and font; and whether they are sent at all, which `is_active` decides
# (staff_rows). `people` can't read the sync app (a higher layer), so the list is written here, and a sync test pins it
# to StaffRecord (test_the_people_app_knows_which_of_a_persons_fields_travel).
FIELDS_ON_STAFF_ROWS = frozenset({"full_name", *OWN_SETTINGS, "is_active"})


def change_person(user: User, *, changed: Collection[str]) -> User:
    """Save a person as the superuser changed them in the admin (apps/people/admin.py): only the fields the form
    changed (`changed`). When one is a field a laptop shows (FIELDS_ON_STAFF_ROWS), each shop where the person works
    gets a line for their job, in the same transaction: `archive` when they are switched off, as no laptop may then
    show them, `upsert` otherwise (SYNC-15). Returns the person as saved."""
    # Only what the form changed, never every column, as Django's own save would: the superuser opens Asha's page in
    # the admin, Meneja fixes her phone on the workers' page meanwhile (PPL-10), and the superuser saves a new
    # language. Saving every column would put the old phone back, quietly, with no line in any audit trail. A field the
    # form holds that is no column of the person (their groups, their admin permissions) the admin saves itself.
    columns = {column.name for column in User._meta.concrete_fields}
    saved = [name for name in changed if name in columns]
    with transaction.atomic():
        if saved:
            user.save(update_fields=saved)
        if FIELDS_ON_STAFF_ROWS & set(changed):
            _record_each_job(user)
    return user


def _record_each_job(user: User) -> None:
    # A person's own row changed, in a way every shop where they work shows on their staff row: their language and font
    # (UI-9), their name or switch-off in the admin, or their name fixed on the workers' page (PPL-10). The person
    # belongs to no shop, so each shop gets a line of its own, naming the person's job there, in the transaction that
    # saved the person (SYNC-15). The shops come from the person's door, ordered by id: read before any shop is open, or
    # inside the visit of the shop where the fix is made (ADR-0044). One block per shop, one after another, never one
    # inside another, each opening its shop over the visit's and handing it back as it ends. Two such saves at once then
    # take the shops' counters in the same order, so neither can hold one counter while waiting for the other's. Each
    # block numbers at its own end and keeps its counter until the commit, a moment later.
    if not transaction.get_connection().in_atomic_block:
        # Outside a transaction, each shop's line would commit alone, and a failure later would leave the person unsaved
        # and some shops' laptops told of a change that never happened. A bug in the calling code, so a server error.
        raise TransactionManagementError("_record_each_job runs inside the transaction that saved the person.")
    # Switched off, they leave every laptop's PIN screen: the bootstrap no longer sends them (staff_rows).
    op = ChangeOp.UPSERT if user.is_active else ChangeOp.ARCHIVE
    for shop_id in shops_of_person(user.pk):
        with shop_context(shop_id), recording_changes(shop_id):
            # Read through the guard, inside this shop: the person's current job here, one at most (the door's rule).
            for job in StaffMember.objects.filter(user_id=user.pk).exclude(status=StaffStatus.LEFT):
                record_change(job, op)


def set_up_shop(
    *,
    name: str,
    code: str,
    sides: Sequence[NewSide],
    kind: ShopKind = ShopKind.LIVE,
    shop_id: uuid.UUID | None = None,
) -> Shop:
    """Make a shop with everything it needs to work, all or nothing: its sides, each with its stock location and
    cash drawer (create_shop, apps/shops/services.py), and its own copy of the six roles. For the superuser and
    system jobs. `shops` may not import `people` (ADR-0035), so the roles are added here, not by create_shop: a
    shop made by create_shop alone has no roles, so nobody may act there. `kind`: live unless the caller says
    otherwise, passed on to create_shop; the demo seed (DATA-1) makes a demo shop. `shop_id`: the new shop's id, for a
    caller that opens the shop's block before the shop exists, as the demo seed does; a new one otherwise."""
    # The id first, so the new shop can be opened, and its block started, before its row exists: the roles' checks read
    # through the guard, and every line of the setup (the sides and their drawers) is numbered once, at the very end,
    # after the roles (SYNC-15). One block around both: if the roles can't be copied, the shop and its sides are taken
    # back too. create_shop's own block joins this one.
    shop_id = uuid.uuid7() if shop_id is None else shop_id
    with shop_context(shop_id), recording_changes(shop_id):
        shop = create_shop(name=name, code=code, sides=sides, kind=kind, shop_id=shop_id)
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


def _check_receiver(staff: StaffMember) -> None:
    # Asked of the person read again and locked (_locked), so a leaving recorded at the same moment either comes first,
    # and is refused here, or waits until this is given. A person who has left gets nothing: a worker who comes back
    # gets a new job (02 §5). A suspended one may: it counts once they are brought back.
    if staff.status == StaffStatus.LEFT:
        raise ValidationError("A person who has left can't be given a role or a permission.", code="staff.left")


def _given_before[R: (RoleAssignment, PermissionGrant)](
    model: type[R], given_id: uuid.UUID | None, staff: StaffMember, **what: object
) -> R | None:
    # The row a give sent before made, if the app's id (ADR-0007) names one: a phone whose answer was lost sends the
    # same give again, and gets what the first made, never role.already_given (PPL-7). Read with the person locked: of
    # two copies of one give sent at the same moment, the second waits for the first's lock, then finds its row here.
    # Looked for before the receiver's, the Owner role's and the giver's checks, as CreateOnceMixin looks first: the
    # row the first send made would fail the checks of its own repeat (the shop's and the demo's come first: they hold
    # for a repeat too). Through the guarded manager, so another shop's row is not seen: its id clashes at the insert,
    # and the route answers id.taken (StaffViewSet). A row of this shop that is not this give, given to someone else
    # or naming another role, key or side (`what`, by the row's own field names): the id is taken too, with the same
    # answer, as nothing about that row is the business of this give, and a page that sent an old id with a new choice
    # must hear that nothing was given, not get the old row back as if it were (PPL-7's review).
    if given_id is None:
        return None
    found = model.objects.filter(pk=given_id).first()
    if found is not None and (
        found.staff_id != staff.pk or any(getattr(found, field) != value for field, value in what.items())
    ):
        raise ValidationError({"id": ValidationError("This id is already in use.", code="id.taken")})
    return found


def _check_no_open_temporary_password(staff: StaffMember, codes: Collection[str], side: Side | None) -> None:
    # The trap (Jack, 4 Nov 2026): Meneja set Juma's temporary password, and still knows it. If Baba gives Juma the pay
    # key now, Meneja could log in as Juma and hold a key the who-may rule kept from him (_check_may_set_password). So
    # while that password is open, a key its setter lacks waits: Juma chooses his own first, or the owner sets a new one
    # himself. Called with the person locked, so set_temporary_password can't slip in between.
    if not User.objects.filter(pk=staff.user_id, must_change_password=True).exists():
        return
    # Who set it is kept in the audit trail. The last line counts, as a later one replaced the password. Across all of
    # the person's jobs here, as the password and the mark belong to the person: someone who left and came back has a
    # new job, and the same password. No line, or nobody named: typed in the admin, by the superuser, who reads every
    # shop's rows anyway. A reset in the admin writes no line, so an earlier setter's line still counts, and the key
    # waits though their password is gone: it fails safe.
    set_by = (
        AuditEvent.objects.filter(
            action=AuditAction.STAFF_TEMPORARY_PASSWORD,
            subject_type=link_type_of(staff),
            subject_id__in=StaffMember.objects.filter(user_id=staff.user_id).values("pk"),
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


def assign_role(
    staff: StaffMember,
    role: Role,
    *,
    side: Side | None,
    by: StaffMember | None,
    given_id: uuid.UUID | None = None,
) -> RoleAssignment:
    """Give a person a role on one side, or on every side (`side=None`), a side added later included. `by`: who
    gives it; None for the system or the superuser. `given_id`: the id the app made for this give (ADR-0007), if it
    made one: the same id sent again answers with the row the first send made. Refused (staff.temporary_password_open)
    while a temporary password someone without those keys set is still open. The Owner role is the superuser's alone
    to give (role.superuser_only, Jack, PPL-7: A). On the demo, the seed's people keep their roles
    (demo.people_fixed)."""
    _check_shop(staff.shop_id, by)
    _check_same_shop(staff, role, side)
    if by is not None:
        # A visitor who gave Asha the Owner's keys, or more, would change her for every other visitor (OPS-3).
        _check_people_fixed_on_demo(staff)
    with recording_changes(staff.shop_id):
        staff = _locked(staff)
        sent_before = _given_before(
            RoleAssignment, given_id, staff, role_id=role.pk, side_id=None if side is None else side.pk
        )
        if sent_before is not None:
            return sent_before
        _check_receiver(staff)
        # The role as stored, read again and locked: the giver's check compares its saved codes, never those of the
        # copy handed in, which may have been changed in memory and never saved (the Owner role made to say
        # "sale.write" would pass as a Seller's). An owner changing the role at the same moment waits until it is
        # given, or this waits for them. no_key, as every office row others link to (03 §5.5): this role's assignments
        # link to it.
        role = Role.objects.select_for_update(no_key=True).get(pk=role.pk)
        if by is not None and role.template == RoleTemplate.OWNER:
            # Whoever holds it can be suspended or changed only by the superuser (_check_may_act_as): a manager who held
            # every key and gave himself, or a friend, the Owner role could no longer be stopped by the owner. Asked
            # before the giver rule, so even an owner hears "ask the superuser", not a plain no (02 §5 v1.39).
            raise ValidationError("Only the superuser gives the Owner role.", code="role.superuser_only")
        _check_giver(by, role.permissions, side)
        _check_no_open_temporary_password(staff, role.permissions, side)
        given = RoleAssignment(shop_id=staff.shop_id, staff=staff, role=role, side=side, created_by=by)
        if given_id is not None:
            # The app's id, not a new one: a repeat then finds this row (_given_before).
            given.id = given_id
        # Every rule in Meta first: the same role twice on one side comes back as a code (role.already_given).
        given.full_clean()
        given.save()
        # The role stays on the server; the keys it gives travel on the person's staff row, so the person is named.
        record_change(staff)
    return given


def grant_permission(
    staff: StaffMember,
    permission: str,
    *,
    side: Side | None,
    by: StaffMember | None,
    granted_id: uuid.UUID | None = None,
) -> PermissionGrant:
    """Give a person one extra permission on one side, or on every side (`side=None`): Juma may count the stock on
    Vyakula. Checked as a role is given (assign_role), the app's id (`granted_id`) and the demo's people included."""
    _check_shop(staff.shop_id, by)
    _check_same_shop(staff, side)
    if by is not None:
        _check_people_fixed_on_demo(staff)
    with recording_changes(staff.shop_id):
        staff = _locked(staff)
        sent_before = _given_before(
            PermissionGrant, granted_id, staff, permission=permission, side_id=None if side is None else side.pk
        )
        if sent_before is not None:
            return sent_before
        _check_receiver(staff)
        _check_giver(by, [permission], side)
        _check_no_open_temporary_password(staff, [permission], side)
        granted = PermissionGrant(shop_id=staff.shop_id, staff=staff, permission=permission, side=side, created_by=by)
        if granted_id is not None:
            granted.id = granted_id
        # A code from the list only (permission.unknown), and once per side (permission.already_given).
        granted.full_clean()
        granted.save()
        # As for a role: the key travels on the person's staff row.
        record_change(staff)
    return granted


def end_role(given: RoleAssignment, *, reason: str, by: StaffMember | None) -> RoleAssignment:
    """Take a role away from a person (02 §5, PPL-7): from now on it opens nothing, and the row stays, ended, with who,
    when and why. Who may is the rule of Simamisha (Jack: A), as for suspend (_locked_for_a_change): staff.manage on the
    whole shop, never one's own, never from someone who holds a key the one acting lacks, never an owner's or an admin
    person's but by the superuser (`by` None). A worker who left keeps theirs, as history. Refused
    (role.already_ended) if someone ended it first."""
    return _end(given, reason=reason, by=by, code="role.already_ended")


def end_permission(granted: PermissionGrant, *, reason: str, by: StaffMember | None) -> PermissionGrant:
    """Take an extra key away from a person, as end_role takes a role (permission.already_ended)."""
    return _end(granted, reason=reason, by=by, code="permission.already_ended")


def _end[R: (RoleAssignment, PermissionGrant)](row: R, *, reason: str, by: StaffMember | None, code: str) -> R:
    # The one way a role or a key ends, for both tables: an edit of the row, never a delete (rule 7).
    _check_shop(row.shop_id, by)
    # Every end asks why (02 §5): checked before anything is locked, as for a suspension.
    _check_reason(reason)
    with recording_changes(row.shop_id):
        # Reused, never copied (the card's Watch out): both jobs locked lightly, in id order, then who may asked on them
        # as they are now, so of a manager ending Asha's role while the owner suspends that manager, one waits for the
        # other, and the second reads what the first wrote. The demo's seed people stay as made there too.
        staff, by = _locked_for_a_change(row.staff, by)
        # A worker who left keeps theirs as they were, as history, even for the superuser: _locked_for_a_change asks
        # this of a person at the shop only. Their job is over, so the end would change nothing they may do.
        if staff.status == StaffStatus.LEFT:
            raise ValidationError("This person has left.", code="staff.left")
        # The row itself, read again and locked after both jobs, in the order every change of a person keeps: of two
        # managers ending it at once, the second waits, then finds it ended. The jobs' locks already make two ends of
        # one person's rows take turns; this lock holds the row for its own sake. A full lock: nothing links to it.
        row = type(row).objects.select_for_update().get(pk=row.pk)
        if row.ended_at is not None:
            raise ValidationError("This was already taken away.", code=code)
        row.ended_at = timezone.now()
        row.ended_by = by
        # Trimmed, as audit() keeps a reason: the rule in Meta refuses a reason of spaces alone, which _check_reason
        # caught first.
        row.end_reason = reason.strip()
        row.full_clean()
        # `by` told to PostgreSQL for the save, so the edit history's line names who ended it, before and after
        # (ADR-0036). No audit line: the row and its history keep who, when and why (PPL-7's card, default).
        with acting_as(by) if by is not None else nullcontext():
            row.save(update_fields=["ended_at", "ended_by", "end_reason"])
        # The person's keys travel on their staff row (SYNC-15): their laptop drops the key at its next sync.
        record_change(staff)
    return row


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


# Django's error reports, which a server will log and send (OPS-10), list each function's local variables when
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


def record_sync(device: Device, *, at: datetime, unsent_count: int, app_version: str, clock_error: timedelta) -> bool:
    """Keep what a laptop said about itself as it pushed at `at` (SYNC-5): how many records it still holds unsent,
    and the app version it runs; and how far its clock was from the server's (SYNC-14), its `sent_at` minus `at`.
    Called by the push at its end, an empty push too (apps/sync/push.py). True when it was written; False when a newer
    push's report is already there."""
    _check_shop(device.shop_id, None)
    # One UPDATE of these four columns, as note_device_seen's: the row's version and `updated_at` stay as they were,
    # so a rename screen opened a minute ago is never refused (409) because the laptop synced, and the edit history
    # skips them (migrations 0013 and 0016). The time is in the UPDATE too: two pushes of one laptop at the same moment,
    # the older one slower, and its older report would say "3 unsent" of a laptop that has sent them all, or an old
    # clock error after the clock was put right. A single UPDATE is atomic on its own, so it needs no transaction of
    # ours.
    older = Q(last_synced_at__isnull=True) | Q(last_synced_at__lte=at)
    written = Device.objects.filter(older, pk=device.pk).update(
        last_synced_at=at, unsent_count=unsent_count, app_version=app_version, clock_error=clock_error
    )
    if written:
        device.last_synced_at, device.unsent_count, device.app_version = at, unsent_count, app_version
        device.clock_error = clock_error
    return bool(written)


@dataclass(frozen=True)
class Outage:
    # One offline period as a laptop reported it at a push (SYNC-5): its id, made on the laptop (ADR-0007), and when
    # its line went and came back, by its clock, in UTC; and whether its real end is unknown, the laptop's app having
    # lost sight of it first (SYNC-14's review). An app from before that says nothing of it: False.
    id: uuid.UUID
    started_at: datetime
    ended_at: datetime
    end_unknown: bool = False


def record_outages(device: Device, outages: Sequence[Outage]) -> None:
    """Keep each offline period a laptop reported at a push, once each (SYNC-5): a push sent again, or a period listed
    twice, keeps one row per id. Called by the push at its end (apps/sync/push.py)."""
    _check_shop(device.shop_id, None)
    # By id, so a period listed twice in one push is one row.
    rows = {
        outage.id: DeviceOutage(
            id=outage.id,
            shop_id=device.shop_id,
            device=device,
            started_at=outage.started_at,
            ended_at=outage.ended_at,
            end_unknown=outage.end_unknown,
        )
        for outage in outages
    }
    # One INSERT ... ON CONFLICT DO NOTHING: an id already kept is left as it is, whichever shop holds it. This shop's
    # is the same period sent again, or a twin push at the same moment; another shop's is left out, with no error and
    # no word of that shop's row, as a report on a laptop's health must never stop its push (03 §5.4). No full_clean:
    # every field is a time or the laptop's own id, checked by the push's route.
    DeviceOutage.objects.bulk_create(rows.values(), ignore_conflicts=True)


def lock_device_numbers(device: Device) -> int | None:
    """The number the device's next record should follow, None if the server never kept one (a new device, or one that
    pushed before SYNC-5), with the device's row locked until the caller's transaction ends (SYNC-5). Two pushes of
    one laptop at the same moment take turns: the second reads the number the first left, not one from before it.
    Called by the push at the start of each record's transaction (apps/sync/push.py)."""
    _check_shop(device.shop_id, None)
    if not transaction.get_connection().in_atomic_block:
        # Outside a transaction the lock would end with this one query, and two pushes could read the same number.
        raise TransactionManagementError("lock_device_numbers locks until the transaction ends: open one first.")
    # no_key, as block's: other visits insert rows that link to the device as this push runs, and each such insert
    # takes a light lock on it (FOR KEY SHARE), which this one lets through: a PIN try on this laptop (PinLock), the
    # audit and edit lines that name it (X3). A full lock would make each of them wait for this whole record's
    # transaction. Another push of this same laptop waits here all the same, as it must (SYNC-5's review).
    return Device.objects.select_for_update(no_key=True).values_list("last_device_seq", flat=True).get(pk=device.pk)


def move_device_number(device: Device, number: int) -> None:
    """Make `number` the one the device's next record should follow. Inside the transaction lock_device_numbers
    locked the row in, so a record rolled back takes its number with it. One UPDATE of this one column, as
    record_sync's: the row's version stays, and the edit history skips it (migration 0014)."""
    _check_shop(device.shop_id, None)
    Device.objects.filter(pk=device.pk).update(last_device_seq=number)
    device.last_device_seq = number


def _set_device_status(
    device: Device, was: DeviceStatus, becomes: DeviceStatus, action: AuditAction, *, by: StaffMember, reason: str
) -> Device:
    # block and unblock are one move each way: active → blocked, blocked → active.
    _check_shop(device.shop_id, by)
    _check_reason(reason, code="device.reason_required")
    with transaction.atomic():
        # The device as stored, read again and locked: its status and home side are checked as they are now, not as
        # the copy handed in says. Two managers blocking at once take turns, and the second finds it blocked. no_key, as
        # in editing(), which locks it again below: a block made on this device names it, and must not wait for this.
        current = Device.objects.select_for_update(no_key=True).get(pk=device.pk)
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
