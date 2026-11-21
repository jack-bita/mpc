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
from pytest_django import Settings

from apps.control.models import EditEvent
from apps.core.acting import acting_as
from apps.core.editing import VersionConflict
from apps.core.permissions import RoleTemplate
from apps.core.tenancy import ShopMismatch, shop_context
from apps.people.models import StaffMember, User
from apps.people.services import add_staff
from apps.shops.models import Shop, Side
from apps.shops.selectors import shop_today
from apps.staffpay.calculations import DayRules
from apps.staffpay.models import AbsenceType, AttendanceDay, DayChoice, DayStatus, ReviewReason
from apps.staffpay.selectors import rules_as_text
from apps.staffpay.services import decide_day

pytestmark = pytest.mark.django_db

GiveRole = Callable[[StaffMember, RoleTemplate, Side | None], None]

MONDAY = dt.date(2026, 11, 16)
SUNDAY = dt.date(2026, 11, 15)
FIRST_FINE = Decimal("500.00")

# The rules Juma's Monday was judged by, as the book kept them with it (T4): the owner's day, a first fine of 500.
MONDAYS_RULES = rules_as_text(
    DayRules(
        on_time_until=dt.time(7, 35),
        second_fine_from=dt.time(8, 0),
        review_from=dt.time(8, 30),
        afternoon_from=dt.time(12, 0),
        midday=dt.time(13, 0),
        morning_leave_until=dt.time(13, 30),
        closing=dt.time(18, 40),
        late_fine=FIRST_FINE,
        second_fine=Decimal("1500.00"),
    )
)


def job(shop: Shop, name: str) -> StaffMember:
    # A job made the way the app makes one: create_user, then the people service, inside the shop (PPL-2).
    user = User.objects.create_user(full_name=f"{name} Demo")
    with shop_context(shop):
        return add_staff(shop=shop, user=user, display_name=name, started_on=dt.date(2026, 1, 1), by=None)


def kept_day(staff: StaffMember, **changes: object) -> AttendanceDay:
    # A day as the book keeps it (ATT-10): Juma's Monday, in at 07:50 and no Toka, sent to review; `changes` overrides
    # a fact. Written past the book, as test_attendance_book.py writes its rows: these tests decide a day, they don't
    # work one out.
    facts: dict[str, object] = {
        "shop_id": staff.shop_id,
        "staff": staff,
        "date": MONDAY,
        "status": DayStatus.NEEDS_REVIEW,
        "fine": Decimal("0.00"),
        "first_in": dt.time(7, 50),
        "first_out": None,
        "rules_used": MONDAYS_RULES,
        "review_reason": ReviewReason.NO_OUT,
    }
    facts.update(changes)
    day = AttendanceDay(**facts)
    day.save()
    return day


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
    # In at 07:50: the first fine, 500, from the rules Monday kept (T4). The shop today has typed no fine at all, so a
    # fine read from today's rules would be 0: the day's own copy is what counts.
    day = kept_day(juma)
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
    day = kept_day(juma, status=DayStatus.ABSENT, first_in=None, review_reason="")
    decide(day, baba, choice, "Alienda benki")
    kept = fresh(day)
    assert (kept.decided_status, kept.absence_type, kept.decided_fine) == (DayStatus.ABSENT, kind, Decimal("0.00"))
    assert kept.status == DayStatus.ABSENT


def test_any_working_day_may_be_decided(baba: StaffMember, juma: StaffMember) -> None:
    # Not only a day to decide: Juma was on time, but Baba sent him home sick at 10:00, so his day is a half day.
    day = kept_day(juma, status=DayStatus.ON_TIME, first_in=dt.time(7, 20), first_out=dt.time(18, 45), review_reason="")
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


def test_a_person_of_another_shop_is_a_bug(staff_b: StaffMember, juma: StaffMember) -> None:
    # The route finds the day and the person in the one shop open, so another shop's person here is a bug in our
    # code (T1): a server error, before anything is read or written.
    day = kept_day(juma)
    with shop_context(day.shop_id), pytest.raises(ShopMismatch):
        decide_day(day, choice=DayChoice.ON_TIME, reason="Alisahau", replaces=None, by=staff_b)


# Which days.


def test_an_off_day_is_not_decided(baba: StaffMember, juma: StaffMember) -> None:
    # A Sunday, or a closed day nobody tapped on, is the shop's calendar: never paid, so nothing to decide (01 §8.1).
    day = kept_day(juma, date=SUNDAY, status=DayStatus.OFF, first_in=None, rules_used={}, review_reason="")
    with pytest.raises(ValidationError) as refused:
        decide(day, baba)
    assert refused.value.code == "day.not_working_day"


def test_today_is_not_decided(baba: StaffMember, juma: StaffMember) -> None:
    # Today isn't over: the book never keeps it (ATT-10), so a row of today is refused all the same.
    with shop_context(juma.shop_id):
        today = shop_today(juma.shop)
    with pytest.raises(ValidationError) as refused:
        decide(kept_day(juma, date=today), baba)
    assert refused.value.code == "day.not_working_day"


def test_late_is_refused_with_no_late_ingia(baba: StaffMember, juma: StaffMember) -> None:
    # Juma's Monday with no Ingia known (a Toka alone): nobody knows when he came, so nobody may fine him as late. Sent
    # all the same, with no reason either: both refused at once, each beside its box, and nothing kept.
    day = kept_day(juma, first_in=None, first_out=dt.time(18, 45), review_reason=ReviewReason.NO_IN)
    with pytest.raises(ValidationError) as refused:
        decide(day, baba, DayChoice.LATE, reason="   ")
    assert codes_of(refused) == {"choice": {"day.choice_not_offered"}, "reason": {"day.reason_missing"}}
    assert fresh(day).decided_status == ""


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
