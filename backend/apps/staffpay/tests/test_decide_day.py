"""apps/staffpay/tests/test_decide_day.py — a person decides what a worker's day was (decide_day, ATT-6; 02 §12).

Juma's Monday waits for a decision: in at 07:50, no Toka. Baba, the owner, opens it and decides:

    the one deciding                         the answer
    Baba, or a manager, on Juma's day        kept, beside what the book said (A2), with its fine, who, when and why
    a manager on his own day                 day.own: the owner decides the manager's days (Jack: A)
    a seller                                 403
    a Sunday, a closed day nobody tapped on  day.not_working_day
    a second manager, a moment later         409: someone decided it since; the page reads it again
    Amechelewa with no late Ingia            day.choice_not_offered
    no reason                                day.reason_missing
    on the demo, a reason typed              demo.ready_reasons: one of three ready ones

A day decided late or half takes the fine its first Ingia gives by the rules that day used (T4), never today's. The
fines are the demo's made-up 500 and 1,500 (rule 10). Fake data only: the repo is public.
"""

import datetime as dt
from collections.abc import Callable
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from pytest_django import Settings

from apps.control.models import EditEvent
from apps.core.acting import acting_as
from apps.core.editing import VersionConflict
from apps.core.permissions import Permission, RoleTemplate
from apps.core.settings_registry import LATE_FINE
from apps.core.tenancy import ShopMismatch, shop_context
from apps.people.models import Device, StaffMember
from apps.people.services import change_worker, grant_permission, hire_again, mark_left, suspend
from apps.shops.models import Shop, Side
from apps.shops.selectors import shop_today
from apps.staffpay.models import (
    AbsenceType,
    AttendanceDay,
    ClockKind,
    DayChoice,
    DayStatus,
    ReviewReason,
)
from apps.staffpay.services import decide_day
from apps.staffpay.tests.days import FIRST_FINE, SUNDAY, absent_day, doubted_tap, job, kept_day, rule, switch_on
from tests.concurrency import in_another_transaction, wait_until_someone_waits_for_me

pytestmark = pytest.mark.django_db

GiveRole = Callable[[StaffMember, RoleTemplate, Side | None], None]


@pytest.fixture(autouse=True)
def the_shops_day(shop_a: Shop, device_a: Device) -> None:
    # The shop switched attendance on in January, with the owner's fines, and keeps its laptop, Laptop ya Dawa, where
    # every tap below is made (days.py).
    switch_on(shop_a)


def decide(
    day: AttendanceDay,
    by: StaffMember,
    choice: DayChoice = DayChoice.ON_TIME,
    reason: str = "Alisahau kubonyeza Toka",
    replaces: dt.datetime | None = None,
) -> AttendanceDay:
    # As the route calls it: inside the shop, in the person's visit, so the edit history names them.
    with shop_context(day.shop_id), acting_as(by):
        return decide_day(day, choice=choice, reason=reason, replaces=replaces, by=by)


def codes_of(refused: pytest.ExceptionInfo[ValidationError]) -> dict[str, set[str]]:
    # Each box's codes, as the sheet shows them beside it.
    return {field: {error.code or "" for error in errors} for field, errors in refused.value.error_dict.items()}


def fresh(day: AttendanceDay) -> AttendanceDay:
    with shop_context(day.shop_id):
        return AttendanceDay.objects.get(pk=day.pk)


@pytest.fixture
def baba(shop_a: Shop, give_role: GiveRole) -> StaffMember:
    # The owner: every key, on the whole shop.
    staff = job(shop_a, "Baba")
    give_role(staff, RoleTemplate.OWNER, None)
    return staff


@pytest.fixture
def meneja(shop_a: Shop, give_role: GiveRole) -> StaffMember:
    # A manager, who holds attendance.manage on the whole shop, as the demo's Meneja does.
    staff = job(shop_a, "Meneja")
    give_role(staff, RoleTemplate.MANAGER, None)
    return staff


@pytest.fixture
def juma(shop_a: Shop, side_a: Side, give_role: GiveRole) -> StaffMember:
    # A seller of the Dawa side.
    staff = job(shop_a, "Juma")
    give_role(staff, RoleTemplate.SELLER, side_a)
    return staff


# A decision kept.


def test_baba_decides_jumas_day_a_full_day(baba: StaffMember, juma: StaffMember) -> None:
    # The card's story: Juma forgot his Toka, and Baba decides his Monday a full day. Kept with who, when and why, and
    # no fine; the book's own answer stays beside it, needs review with no Toka (A2).
    day = kept_day(juma)
    decide(day, baba)
    kept = fresh(day)
    assert (kept.decided_status, kept.absence_type, kept.decided_fine) == (DayStatus.ON_TIME, "", Decimal("0.00"))
    assert (kept.decided_by_id, kept.decision_reason) == (baba.pk, "Alisahau kubonyeza Toka")
    assert kept.decided_at is not None
    assert (kept.status, kept.review_reason, kept.fine) == (DayStatus.NEEDS_REVIEW, ReviewReason.NO_OUT, Decimal("0"))


def test_a_manager_decides_a_workers_day(meneja: StaffMember, juma: StaffMember) -> None:
    # attendance.manage is the manager's too: Meneja decides Juma's Monday, as on the demo.
    decide(kept_day(juma), meneja)


def test_a_day_decided_late_takes_its_fine_from_its_own_rules(baba: StaffMember, juma: StaffMember) -> None:
    # In at 07:50: the first fine, 500, from the rules Monday kept (T4). The owner raised it to 2,000 from today, so a
    # fine read from today's rules would be 2,000: the day's own copy is what counts.
    day = kept_day(juma)
    with shop_context(juma.shop_id):
        today = shop_today(juma.shop)
    rule(juma.shop, LATE_FINE, Decimal("2000.00"), today)
    decide(day, baba, DayChoice.LATE, "Alichelewa, hakubonyeza Toka")
    kept = fresh(day)
    assert (kept.decided_status, kept.decided_fine) == (DayStatus.LATE, FIRST_FINE)


def test_a_day_decided_half_keeps_a_late_arrivals_fine(baba: StaffMember, juma: StaffMember) -> None:
    # In at 07:50, gone at lunch: the morning's half, less the first fine, as the rule's own half does (ATT-4).
    day = kept_day(juma)
    decide(day, baba, DayChoice.HALF, "Aliondoka mchana")
    assert (fresh(day).decided_status, fresh(day).decided_fine) == (DayStatus.HALF, FIRST_FINE)


@pytest.mark.parametrize(
    ("choice", "kind"),
    [
        (DayChoice.OFFICE_DUTY, AbsenceType.OFFICE_DUTY),
        (DayChoice.PERMISSION, AbsenceType.PERMISSION),
        (DayChoice.NO_SHOW, AbsenceType.NO_SHOW),
    ],
)
def test_an_absence_keeps_its_kind(baba: StaffMember, juma: StaffMember, choice: DayChoice, kind: AbsenceType) -> None:
    # Juma never tapped on Monday: absent, unpaid, until Baba says why. Sent to the bank, it is office duty, paid as a
    # full day (WAGE-2); allowed to stay home, permission; no word, a no-show. Each kept as absent, with its kind.
    day = absent_day(juma)
    decide(day, baba, choice, "Alienda benki")
    kept = fresh(day)
    assert (kept.decided_status, kept.absence_type, kept.decided_fine) == (DayStatus.ABSENT, kind, Decimal("0.00"))
    assert kept.status == DayStatus.ABSENT


def test_any_working_day_may_be_decided(baba: StaffMember, juma: StaffMember) -> None:
    # Not only a day to decide: Juma was on time, but Baba sent him home sick at 10:00, so his day is a half day.
    day = kept_day(juma, (ClockKind.IN, 7, 20), (ClockKind.OUT, 18, 45))
    decide(day, baba, DayChoice.HALF, "Aliumwa, akarudi nyumbani")
    assert (fresh(day).decided_status, fresh(day).decided_fine) == (DayStatus.HALF, Decimal("0.00"))


def test_a_reason_is_kept_without_its_spaces(baba: StaffMember, juma: StaffMember) -> None:
    day = kept_day(juma)
    decide(day, baba, reason="  Alisahau kubonyeza Toka  ")
    assert fresh(day).decision_reason == "Alisahau kubonyeza Toka"


# A decision changed.


def test_a_decision_changed_keeps_the_one_before(baba: StaffMember, juma: StaffMember) -> None:
    # Baba decided Juma's Monday a full day; Juma owns up that he left at 13:10, so Baba decides again, a half day, on
    # the page that showed his first decision. The second writes over the first, and the edit history keeps the first
    # (ADR-0036), naming Baba.
    day = kept_day(juma)
    first = decide(day, baba)
    decide(day, baba, DayChoice.HALF, "Aliondoka saa 7 mchana", replaces=first.decided_at)
    assert fresh(day).decided_status == DayStatus.HALF
    with shop_context(day.shop_id):
        changes = list(
            EditEvent.objects.filter(subject_type="attendance_day", subject_id=day.pk).order_by("created_at")
        )
    assert [(edit.before["decided_status"], edit.after["decided_status"]) for edit in changes] == [
        ("", DayStatus.ON_TIME),
        (DayStatus.ON_TIME, DayStatus.HALF),
    ]
    assert {edit.created_by_id for edit in changes} == {baba.pk}


def test_a_second_manager_is_told_someone_decided_since(
    baba: StaffMember, meneja: StaffMember, juma: StaffMember
) -> None:
    # Baba and Meneja open Juma's Monday at the same moment, neither seeing a decision. Baba saves first: a full day.
    # Meneja's half day would write over a decision he never saw, so it is refused (409), and Baba's stays.
    day = kept_day(juma)
    decide(day, baba)
    with pytest.raises(VersionConflict):
        decide(day, meneja, DayChoice.HALF, "Aliondoka mchana")
    assert (fresh(day).decided_status, fresh(day).decided_by_id) == (DayStatus.ON_TIME, baba.pk)


def test_a_change_names_the_decision_it_replaces(baba: StaffMember, juma: StaffMember) -> None:
    # A page that saw a decision, sending none (an old page), or one that never was, is refused the same way.
    day = kept_day(juma)
    first = decide(day, baba)
    assert first.decided_at is not None
    with pytest.raises(VersionConflict):
        decide(day, baba, DayChoice.HALF, "Aliondoka mchana", replaces=first.decided_at - dt.timedelta(seconds=1))


def test_the_same_decision_sent_again_is_answered_as_done(
    baba: StaffMember, meneja: StaffMember, juma: StaffMember
) -> None:
    # Baba saves a full day; the network loses the answer, and his phone sends it again, still saying it saw no
    # decision. It is his own, the same choice and reason: answered as done, nothing written again, one line in the
    # edit history. Not so a different reason of his, nor the same words from Meneja: those are refused as before.
    day = kept_day(juma)
    first = decide(day, baba)
    again = decide(day, baba)
    assert again.decided_at == first.decided_at
    with shop_context(day.shop_id):
        assert EditEvent.objects.filter(subject_type="attendance_day", subject_id=day.pk).count() == 1
    with pytest.raises(VersionConflict):
        decide(day, baba, reason="Sababu nyingine")
    with pytest.raises(VersionConflict):
        decide(day, meneja)


def _decide_in_another_visit(day: AttendanceDay, by: StaffMember, choice: DayChoice) -> object:
    # A decision in a transaction of its own, on a connection of its own, as a second manager's phone sends one: what it
    # answers, the decision's status, or the refusal it raised, which in_another_transaction hands back to the test.
    with shop_context(day.shop_id):
        return decide_day(day, choice=choice, reason="Uamuzi wa pili", replaces=None, by=by).decided_status


@pytest.mark.django_db(transaction=True)
def test_two_managers_at_once_take_turns(baba: StaffMember, meneja: StaffMember, juma: StaffMember) -> None:
    # Baba and Meneja both tap Hifadhi on Juma's Monday at the same moment, each having seen no decision. Baba's is
    # under way, holding the locks it takes, when Meneja's arrives: it must wait for Baba's to be saved, then find his
    # decision there and be refused (409), never pass its check before Baba's lands and write over it. Without the
    # locks, Meneja's would read the day as it was, with no decision, and save its half day over Baba's full one.
    day = kept_day(juma)
    with shop_context(day.shop_id), transaction.atomic():
        decide_day(day, choice=DayChoice.ON_TIME, reason="Alisahau kubonyeza Toka", replaces=None, by=baba)
        second, ended = in_another_transaction(lambda: _decide_in_another_visit(day, meneja, DayChoice.HALF))
        # Meneja's truly waits on the locks: committed earlier, it would run after, and pass with no lock at all.
        wait_until_someone_waits_for_me()
    second.join(timeout=10)
    assert len(ended) == 1 and isinstance(ended[0], VersionConflict)
    assert (fresh(day).decided_status, fresh(day).decided_by_id) == (DayStatus.ON_TIME, baba.pk)


@pytest.mark.django_db(transaction=True)
def test_a_decision_waits_for_the_book_and_reads_its_day_afresh(baba: StaffMember, juma: StaffMember) -> None:
    # A manager opens the month, and the book is working it out, holding the shop's jobs, when Baba decides Juma's
    # Monday; meanwhile Juma's Toka arrives from a laptop that was offline. Baba's decision waits for the book, then
    # works the day out again itself, with the Toka: the day it decides is late (in at 07:50, out at 18:45), as the
    # book now says, not the "no Toka" it was a moment before.
    day = kept_day(juma)
    with shop_context(day.shop_id), transaction.atomic():
        list(StaffMember.objects.filter(shop=day.shop_id).order_by("pk").select_for_update(no_key=True))
        second, ended = in_another_transaction(lambda: _decide_in_another_visit(day, baba, DayChoice.HALF))
        wait_until_someone_waits_for_me()
        kept_day(juma, (ClockKind.OUT, 18, 45))
    second.join(timeout=10)
    assert ended == [DayStatus.HALF]
    assert (fresh(day).status, fresh(day).review_reason) == (DayStatus.LATE, "")


# Who may.


def test_nobody_decides_their_own_day(baba: StaffMember, meneja: StaffMember) -> None:
    # Meneja came in at 07:50 and never tapped Toka: his own Monday is not his to decide, or he would take his own fine
    # off (Jack: A). The owner decides it.
    day = kept_day(meneja)
    with pytest.raises(ValidationError) as refused:
        decide(day, meneja)
    assert refused.value.code == "day.own"
    assert fresh(day).decided_status == ""
    decide(day, baba)
    assert fresh(day).decided_by_id == baba.pk


def test_a_seller_is_refused(shop_a: Shop, side_a: Side, give_role: GiveRole, juma: StaffMember) -> None:
    # Asha sells on the Dawa side: she holds no attendance.manage, so she may not decide Juma's day.
    asha = job(shop_a, "Asha")
    give_role(asha, RoleTemplate.SELLER, side_a)
    with pytest.raises(PermissionDenied):
        decide(kept_day(juma), asha)


def test_a_suspended_manager_is_refused(meneja: StaffMember, juma: StaffMember) -> None:
    # Meneja is suspended this morning: his keys stop at once (X2), read afresh inside the decision, so he may not
    # decide Juma's day, though his copy of himself, loaded before the suspension, still says "active".
    with shop_context(meneja.shop_id):
        suspend(meneja, by=None, reason="Uchunguzi wa hesabu")
    with pytest.raises(PermissionDenied):
        decide(kept_day(juma), meneja)


def test_a_key_on_one_side_decides_nothing(shop_a: Shop, side_a: Side, juma: StaffMember) -> None:
    # Hamisi may fix attendance on Dawa only (X1): attendance is the whole shop's, as one list holds Dawa's Juma and
    # Vyakula's Baraka, so a key on one side decides no day at all.
    hamisi = job(shop_a, "Hamisi")
    with shop_context(shop_a):
        grant_permission(hamisi, Permission.ATTENDANCE_MANAGE, side=side_a, by=None)
    with pytest.raises(PermissionDenied):
        decide(kept_day(juma), hamisi)


def test_a_person_hired_again_decides_neither_jobs_day(shop_a: Shop, give_role: GiveRole, baba: StaffMember) -> None:
    # Baraka sold until Tuesday 17th, and comes back on the 18th as a manager (PPL-11): one person, two jobs. His old
    # job's Monday waits for a decision, and his new job holds the key, but the day is still his own, so the owner
    # decides it: the rule reads the person, never the job (Jack: A).
    old = job(shop_a, "Baraka")
    day = kept_day(old)
    with shop_context(shop_a):
        mark_left(old, left_on=dt.date(2026, 11, 17), by=None, reason="Ameacha kazi")
        old.refresh_from_db()
        new = hire_again(old, display_name="Baraka", started_on=dt.date(2026, 11, 18), by=None)
    give_role(new, RoleTemplate.MANAGER, None)
    with pytest.raises(ValidationError) as refused:
        decide(day, new)
    assert refused.value.code == "day.own"
    decide(day, baba)


def test_a_person_of_another_shop_is_a_bug(staff_b: StaffMember, juma: StaffMember) -> None:
    # The route finds the day and the person in the one shop open, so another shop's person here is a bug in our
    # code (T1): a server error, before anything is read or written.
    day = kept_day(juma)
    with shop_context(day.shop_id), pytest.raises(ShopMismatch):
        decide_day(day, choice=DayChoice.ON_TIME, reason="Alisahau", replaces=None, by=staff_b)


# Which days.


def test_an_off_day_is_not_decided(baba: StaffMember, juma: StaffMember) -> None:
    # A Sunday, or a closed day nobody tapped on, is the shop's calendar: never paid, so nothing to decide (01 §8.1).
    day = absent_day(juma, SUNDAY)
    assert day.status == DayStatus.OFF
    with pytest.raises(ValidationError) as refused:
        decide(day, baba)
    assert refused.value.code == "day.not_working_day"


def test_today_is_not_decided(baba: StaffMember, juma: StaffMember) -> None:
    # Today isn't over: the book never keeps it (ATT-10), so a row of today is refused all the same.
    with shop_context(juma.shop_id):
        today = shop_today(juma.shop)
        # Written past the book, which never keeps today: a row of today could only come from a bug.
        row = AttendanceDay.objects.create(
            shop_id=juma.shop_id,
            staff=juma,
            date=today,
            status=DayStatus.ABSENT,
            fine=Decimal("0.00"),
            rules_used={"late_fine": "500.00"},
        )
    with pytest.raises(ValidationError) as refused:
        decide(row, baba)
    assert refused.value.code == "day.not_working_day"


def test_a_day_the_book_no_longer_answers_is_not_decided(baba: StaffMember, juma: StaffMember) -> None:
    # Juma's Monday was kept, absent; then his first day was fixed to Wednesday 18th (PPL-10). The row stays (rule 7),
    # but the book no longer reads it, so a decision on it would count for nothing: refused, as a day that isn't one of
    # his working days. The page never offers one; a request typed by hand meets this (ATT-6's review).
    day = absent_day(juma)
    with shop_context(juma.shop_id):
        change_worker(juma, version=juma.version, reason="Alianza Jumatano", by=None, started_on=dt.date(2026, 11, 18))
    with pytest.raises(ValidationError) as refused:
        decide(day, baba)
    assert refused.value.code == "day.not_working_day"
    assert fresh(day).decided_status == ""


def test_late_is_refused_with_no_late_ingia(baba: StaffMember, juma: StaffMember) -> None:
    # Juma's Monday with no Ingia known (a Toka alone): nobody knows when he came, so nobody may fine him as late. Sent
    # all the same, with no reason either: both refused at once, each beside its box, and nothing kept.
    day = kept_day(juma, (ClockKind.OUT, 18, 45))
    assert day.review_reason == ReviewReason.NO_IN
    with pytest.raises(ValidationError) as refused:
        decide(day, baba, DayChoice.LATE, reason="   ")
    assert codes_of(refused) == {"choice": {"day.choice_not_offered"}, "reason": {"day.reason_missing"}}
    assert fresh(day).decided_status == ""


def test_a_day_whose_time_is_in_doubt_takes_no_fine(baba: StaffMember, juma: StaffMember) -> None:
    # Juma's Monday: an Ingia at 07:20 whose time the server can't trust, then one at 07:50 that it does. Nobody knows
    # when he came, so the day can't be decided late from 07:50 (Jack: A); a half day takes no fine.
    doubted_tap(juma, 7, 20)
    day = kept_day(juma)
    assert day.review_reason == ReviewReason.TIME_UNKNOWN
    with pytest.raises(ValidationError) as refused:
        decide(day, baba, DayChoice.LATE, "Alichelewa")
    assert codes_of(refused) == {"choice": {"day.choice_not_offered"}}
    decide(day, baba, DayChoice.HALF, "Aliondoka mchana")
    assert (fresh(day).decided_status, fresh(day).decided_fine) == (DayStatus.HALF, Decimal("0.00"))


# The demo.


def test_on_the_demo_a_reason_is_a_ready_one(settings: Settings, baba: StaffMember, juma: StaffMember) -> None:
    # Every visitor logs in as Meneja (OPS-3): a typed reason would show to every visitor after them, so the sheet
    # offers three ready ones (Jack: A), and anything else is refused. A ready one is kept as its code.
    settings.DEMO_SEED = True
    day = kept_day(juma)
    with pytest.raises(ValidationError) as refused:
        decide(day, baba, reason="Maneno ya mgeni")
    assert codes_of(refused) == {"reason": {"demo.ready_reasons"}}
    decide(day, baba, reason="forgot_toka")
    assert fresh(day).decision_reason == "forgot_toka"
