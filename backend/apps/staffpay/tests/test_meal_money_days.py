"""apps/staffpay/tests/test_meal_money_days.py — the meal money of any days, as Hela ya chakula shows it (WAGE-7;
02 §12): meal_money_days (apps/staffpay/services/money.py).

Today is Tuesday 24 November 2026 at MPC, at 10:00:

    Jumanne 24/11 (leo)   9,000   today isn't over: not split yet
    Jumatatu 23/11        8,000   2 share it, 4,000 each; 30,000 crossed out
    Jumamosi 21/11            —   workers came, and nobody typed any: Haijaandikwa
    Ijumaa 20/11          7,000   1 shares it, 7,000; 1 waits for a decision
    Jumla                24,000

What the book keeps on each worker's day is test_attendance_book.py's; what may be typed, test_record_meal_money.py's;
here, only what the page is told. The clock is fixed, so the days are the same whenever the tests run. The amounts are
made up (rule 10). Fake data only: the repo is public.
"""

import datetime as dt
import uuid
from collections.abc import Callable
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from pytest_django import Settings

from apps.core.permissions import RoleTemplate
from apps.core.settings_registry import ATTENDANCE_ON
from apps.core.tenancy import ShopMismatch, shop_context
from apps.people.models import Device, StaffMember
from apps.people.services import hire_again, mark_left
from apps.shops.models import Closure, Shop, Side
from apps.staffpay.models import AttendanceDay, ClockKind, DayChoice, MealMoney
from apps.staffpay.services import (
    MealDay,
    MealMoneyDays,
    decide_day,
    meal_money_days,
    record_meal_money,
    set_pay_rate,
    void_meal_money,
    work_out_days,
)
from apps.staffpay.services import money as money_services
from apps.staffpay.tests.days import JAN_1, job, kept_day, rule, switch_on

pytestmark = pytest.mark.django_db

GiveRole = Callable[[StaffMember, RoleTemplate, Side | None], None]

FRIDAY = dt.date(2026, 11, 20)
SATURDAY = dt.date(2026, 11, 21)
SUNDAY = dt.date(2026, 11, 22)
MONDAY = dt.date(2026, 11, 23)
TODAY = dt.date(2026, 11, 24)
NOV_1 = dt.date(2026, 11, 1)
NOV_30 = dt.date(2026, 11, 30)
# A full day's taps, as kept_day takes them.
FULL_DAY = ((ClockKind.IN, 7, 20), (ClockKind.OUT, 18, 45))


@pytest.fixture(autouse=True)
def tuesday_morning(monkeypatch: pytest.MonkeyPatch, shop_a: Shop, device_a: Device) -> None:
    # 10:00 on Tuesday 24 November in Arusha, 07:00 in UTC, for every read of the clock. The shop switched attendance on
    # on Friday 20 November, so no day before it is anyone's, and its laptop is where every tap below is made (days.py).
    monkeypatch.setattr(timezone, "now", lambda: dt.datetime(2026, 11, 24, 7, 0, tzinfo=dt.UTC))
    rule(shop_a, ATTENDANCE_ON, True, FRIDAY)


@pytest.fixture
def baba(shop_a: Shop, give_role: GiveRole) -> StaffMember:
    # The owner: he holds the key, and is paid by no day, so he shares nothing.
    staff = job(shop_a, "Baba")
    give_role(staff, RoleTemplate.OWNER, None)
    return staff


def paid(shop: Shop, name: str, *, shares_meals: bool = True) -> StaffMember:
    # A worker since January, paid a made-up daily rate from then on (WAGE-1), who shares the meals or cooks them.
    staff = job(shop, name)
    with shop_context(shop):
        set_pay_rate(staff, daily_rate=Decimal("10000"), effective_from=JAN_1, shares_meals=shares_meals, by=None)
    return staff


@pytest.fixture
def asha(shop_a: Shop) -> StaffMember:
    return paid(shop_a, "Asha")


@pytest.fixture
def juma(shop_a: Shop) -> StaffMember:
    return paid(shop_a, "Juma")


def typed(by: StaffMember, day: dt.date, amount: str, note: str = "") -> MealMoney:
    with shop_context(by.shop_id):
        shop = Shop.objects.get(pk=by.shop_id)
        return record_meal_money(shop, money_id=uuid.uuid7(), date=day, amount=Decimal(amount), note=note, by=by)


def days_of(shop: Shop, first: dt.date = NOV_1, last: dt.date = NOV_30) -> MealMoneyDays:
    with shop_context(shop):
        return meal_money_days(shop, first, last)


def by_date(answer: MealMoneyDays) -> dict[dt.date, MealDay]:
    return {day.date: day for day in answer.days}


def test_the_days_of_november_as_jack_drew_them(
    shop_a: Shop, baba: StaffMember, asha: StaffMember, juma: StaffMember
) -> None:
    # The table above, from the taps and the rows.
    cook = paid(shop_a, "Mpishi", shares_meals=False)
    for day in (FRIDAY, SATURDAY, MONDAY):
        kept_day(asha, *FULL_DAY, date=day)
        kept_day(cook, *FULL_DAY, date=day)
    kept_day(juma, (ClockKind.IN, 7, 20), date=FRIDAY)
    kept_day(juma, *FULL_DAY, date=MONDAY)
    typed(baba, FRIDAY, "7000")
    typed(baba, MONDAY, "5000", "Unga na maharage")
    wrong = typed(baba, MONDAY, "30000", "Nyama")
    with shop_context(shop_a):
        void_meal_money(wrong, reason="Sifuri moja zaidi", by=baba)
    typed(baba, MONDAY, "3000", "Nyama")
    typed(baba, TODAY, "9000")

    answer = days_of(shop_a)

    assert (answer.first, answer.last, answer.today) == (NOV_1, TODAY, TODAY)
    assert answer.total == Decimal("24000.00")
    lines = [(day.date, day.amount, day.over, day.sharers, day.share, day.waiting) for day in answer.days]
    # Newest first, as the page lists them, and no Sunday.
    assert lines == [
        (TODAY, Decimal("9000"), False, 0, Decimal("0"), 0),
        (MONDAY, Decimal("8000"), True, 2, Decimal("4000"), 0),
        (SATURDAY, Decimal("0"), True, 1, Decimal("0"), 0),
        (FRIDAY, Decimal("7000"), True, 1, Decimal("7000"), 1),
    ]


def test_the_share_shown_is_the_one_kept(shop_a: Shop, baba: StaffMember, asha: StaffMember, juma: StaffMember) -> None:
    # The page never works a share out: it shows what the book kept on each worker's day, which the pay takes off
    # (WAGE-2).
    for each in (asha, juma, paid(shop_a, "Neema")):
        kept_day(each, *FULL_DAY, date=MONDAY)
    typed(baba, MONDAY, "1000")
    shown = by_date(days_of(shop_a))[MONDAY]
    with shop_context(shop_a):
        kept = set(
            AttendanceDay.objects.filter(date=MONDAY, staff__in=[asha, juma]).values_list("meal_share", flat=True)
        )
    assert kept == {shown.share} == {Decimal("333.00")}
    assert shown.sharers == 3


def test_a_days_rows_say_who_and_when_and_stay_when_crossed_out(shop_a: Shop, baba: StaffMember) -> None:
    # Oldest first, as they were typed; a crossed-out one among them, with who, when and why, for the page to strike
    # through (A2).
    flour = typed(baba, MONDAY, "5000", "Unga na maharage")
    wrong = typed(baba, MONDAY, "30000", "Nyama")
    with shop_context(shop_a):
        void_meal_money(wrong, reason="Sifuri moja zaidi", by=baba)
    rows = by_date(days_of(shop_a))[MONDAY].rows
    assert [(row.id, row.amount, row.note, row.by) for row in rows] == [
        (flour.pk, Decimal("5000"), "Unga na maharage", "Baba"),
        (wrong.pk, Decimal("30000"), "Nyama", "Baba"),
    ]
    assert rows[0].at == flour.created_at
    assert rows[0].voided is None
    stamp = rows[1].voided
    assert stamp is not None
    assert (stamp.by, stamp.reason) == ("Baba", "Sifuri moja zaidi")
    assert stamp.at is not None


def test_a_forgotten_day_is_answered_with_no_money(shop_a: Shop, asha: StaffMember) -> None:
    # Asha came on Friday and nobody typed its money: the page says Haijaandikwa, so the owner sees the forgotten day.
    kept_day(asha, *FULL_DAY, date=FRIDAY)
    friday = by_date(days_of(shop_a))[FRIDAY]
    assert (friday.amount, friday.sharers, friday.rows) == (Decimal("0"), 1, [])
    # A day that waits counts too: someone may have eaten.
    juma = paid(shop_a, "Juma")
    kept_day(juma, (ClockKind.IN, 7, 20), date=SATURDAY)
    saturday = by_date(days_of(shop_a))[SATURDAY]
    assert (saturday.amount, saturday.sharers, saturday.waiting) == (Decimal("0"), 0, 1)


def test_a_day_nobody_came_is_not_called_forgotten(shop_a: Shop, asha: StaffMember, juma: StaffMember) -> None:
    # Nobody who shares the meals came on Friday, only the cook; Monday was closed for a funeral; Sunday the shop is
    # shut; before Friday attendance was off. None of them is a day whose money was forgotten.
    cook = paid(shop_a, "Mpishi", shares_meals=False)
    kept_day(cook, *FULL_DAY, date=FRIDAY)
    with shop_context(shop_a):
        Closure(shop=shop_a, name="Msiba", first_day=MONDAY, last_day=MONDAY).save()
    assert set(by_date(days_of(shop_a))) == {TODAY}


def test_money_nobody_can_share_is_still_shown(shop_a: Shop, baba: StaffMember, asha: StaffMember) -> None:
    # Typed for Friday, when nobody came: the page says Hakuna wa kuchangia, and the total still counts it.
    typed(baba, FRIDAY, "7000")
    answer = days_of(shop_a)
    friday = by_date(answer)[FRIDAY]
    assert (friday.amount, friday.sharers, friday.share) == (Decimal("7000"), 0, Decimal("0"))
    assert answer.total == Decimal("7000")


def test_a_day_whose_every_row_is_crossed_out_is_still_shown(shop_a: Shop, baba: StaffMember) -> None:
    # Nobody came on Friday, and its one row was a slip: crossed out, it must still be seen (A2).
    row = typed(baba, FRIDAY, "7000")
    with shop_context(shop_a):
        void_meal_money(row, reason="Siku nyingine", by=baba)
    friday = by_date(days_of(shop_a))[FRIDAY]
    assert (friday.amount, len(friday.rows)) == (Decimal("0"), 1)


def test_today_is_shown_before_it_is_split(shop_a: Shop, baba: StaffMember, asha: StaffMember) -> None:
    # Today isn't over: the book keeps no day of it, so its money waits to be split, and with none typed it is listed
    # all the same, as today is when it is typed.
    today = by_date(days_of(shop_a))[TODAY]
    assert (today.over, today.amount, today.sharers) == (False, Decimal("0"), 0)
    typed(baba, TODAY, "9000")
    today = by_date(days_of(shop_a))[TODAY]
    assert (today.over, today.amount, today.sharers, today.share) == (False, Decimal("9000"), 0, Decimal("0"))


@pytest.mark.parametrize("why", ["closed", "off"])
def test_today_is_not_listed_when_no_one_works(shop_a: Shop, baba: StaffMember, why: str) -> None:
    # A funeral today, or attendance switched off from today: no meals to type, until someone types some anyway.
    if why == "off":
        rule(shop_a, ATTENDANCE_ON, False, TODAY)
    else:
        with shop_context(shop_a):
            Closure(shop=shop_a, name="Msiba", first_day=TODAY, last_day=TODAY).save()
    assert TODAY not in by_date(days_of(shop_a))
    if why == "closed":
        typed(baba, TODAY, "2000")
        assert by_date(days_of(shop_a))[TODAY].amount == Decimal("2000")


def test_a_sunday_today_is_not_listed(shop_a: Shop, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(timezone, "now", lambda: dt.datetime(2026, 11, 22, 7, 0, tzinfo=dt.UTC))
    assert days_of(shop_a).days == []


def test_only_the_days_asked_for_are_added_up(shop_a: Shop, baba: StaffMember) -> None:
    # Meneja wants 20/11 to 23/11, and the whole of it (Jack, 24 Nov 2026): 15,000. And one day, both ends the same.
    typed(baba, FRIDAY, "7000")
    typed(baba, MONDAY, "8000")
    typed(baba, TODAY, "9000")
    asked = days_of(shop_a, FRIDAY, MONDAY)
    assert (asked.total, [day.date for day in asked.days]) == (Decimal("15000"), [MONDAY, FRIDAY])
    one = days_of(shop_a, MONDAY, MONDAY)
    assert (one.first, one.last, one.total) == (MONDAY, MONDAY, Decimal("8000"))


def test_days_to_come_hold_nothing(shop_a: Shop, asha: StaffMember) -> None:
    # A span that reaches past today is counted up to today; one that starts after it is empty, and answered as it was
    # asked: "25/11 hadi 30/11", never a last day before its first (WAGE-7's review).
    assert days_of(shop_a, TODAY, NOV_30).last == TODAY
    tomorrow = TODAY + dt.timedelta(days=1)
    to_come = days_of(shop_a, tomorrow, NOV_30)
    assert (to_come.first, to_come.last, to_come.days, to_come.total) == (tomorrow, NOV_30, [], Decimal("0"))


def test_the_calendars_first_day_is_no_mistake(shop_a: Shop) -> None:
    # The service steps from day to day, and never past the first one Python knows (WAGE-7's review). The route takes no
    # day before 2000; the book is asked here for no working day, as attendance is off all along.
    with shop_context(shop_a):
        assert money_services._dates_back(dt.date.min, dt.date(1, 1, 3)) == [
            dt.date(1, 1, 3),
            dt.date(1, 1, 2),
            dt.date.min,
        ]


def test_a_rate_typed_between_the_two_reads_never_shows_nothing_each(
    shop_a: Shop, baba: StaffMember, asha: StaffMember, juma: StaffMember, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Asha's rate is typed a moment after the book worked Monday out without it, and before the page reads the rates:
    # she shares the meals by then, and her kept share is still 0. The page shows what Juma was split, never "TSh 0 kila
    # mmoja", until it asks again (WAGE-7's review). Here the book's answer is the one from before her rate.
    for each in (asha, juma):
        kept_day(each, *FULL_DAY, date=MONDAY)
    typed(baba, MONDAY, "2000")
    with shop_context(shop_a):
        before = work_out_days(shop_a, MONDAY, MONDAY)
        AttendanceDay.objects.filter(date=MONDAY, staff=asha).update(meal_share=Decimal("0"))
        for day in before:
            if day.staff_id == asha.pk:
                day.meal_share = Decimal("0")
    monkeypatch.setattr(money_services, "work_out_days", lambda *_args: before)
    monday = by_date(days_of(shop_a, MONDAY, MONDAY))[MONDAY]
    assert (monday.sharers, monday.share) == (2, Decimal("1000"))


def test_a_decision_moves_the_split(shop_a: Shop, baba: StaffMember, asha: StaffMember, juma: StaffMember) -> None:
    # Juma's Friday waits, and Asha pays 7,000; Baba decides he came, and it is 3,500 each.
    kept_day(asha, *FULL_DAY, date=FRIDAY)
    waits = kept_day(juma, (ClockKind.IN, 7, 20), date=FRIDAY)
    typed(baba, FRIDAY, "7000")
    with shop_context(shop_a):
        decide_day(waits, choice=DayChoice.ON_TIME, reason="Alisahau Toka", replaces=None, by=baba)
    friday = by_date(days_of(shop_a))[FRIDAY]
    assert (friday.sharers, friday.share, friday.waiting) == (2, Decimal("3500"), 0)


def test_one_hired_again_the_same_day_counts_once(
    shop_a: Shop, device_a: Device, baba: StaffMember, asha: StaffMember, juma: StaffMember
) -> None:
    # Juma left on Monday and was hired again the same day (PPL-11), and tapped on both jobs: one person waits, not two;
    # and once one of his days is decided, two share Monday's money and nobody waits (Jack: A, 25 Nov 2026).
    kept_day(asha, *FULL_DAY, date=MONDAY)
    waits = kept_day(juma, (ClockKind.IN, 7, 20), date=MONDAY)
    with shop_context(shop_a):
        mark_left(juma, left_on=MONDAY, by=None, reason="Ameacha kazi")
        juma.refresh_from_db()
        again = hire_again(juma, display_name="Juma", started_on=MONDAY, by=None)
        set_pay_rate(again, daily_rate=Decimal("10000"), effective_from=MONDAY, by=None)
    kept_day(again, (ClockKind.OUT, 18, 45), date=MONDAY)
    typed(baba, MONDAY, "2000")
    monday = by_date(days_of(shop_a))[MONDAY]
    assert (monday.sharers, monday.share, monday.waiting) == (1, Decimal("2000"), 1)
    with shop_context(shop_a):
        decide_day(waits, choice=DayChoice.HALF, reason="Aliondoka mchana", replaces=None, by=baba)
    monday = by_date(days_of(shop_a))[MONDAY]
    assert (monday.sharers, monday.share, monday.waiting) == (2, Decimal("1000"), 0)


def test_the_days_are_read_in_a_few_queries(shop_a: Shop, baba: StaffMember, asha: StaffMember) -> None:
    # However many rows and days: the book's own reads, the money, the rates and the shop's rules, once each. Who typed
    # each row comes with it.
    for day in (FRIDAY, SATURDAY, MONDAY):
        kept_day(asha, *FULL_DAY, date=day)
        for _ in range(5):
            typed(baba, day, "1000")
    days_of(shop_a)
    with CaptureQueriesContext(connection) as queries:
        answer = days_of(shop_a)
    assert sum(len(day.rows) for day in answer.days) == 15
    assert len(queries) <= 20


def test_another_shops_money_is_never_shown(
    shop_a: Shop, shop_b: Shop, baba: StaffMember, staff_b: StaffMember
) -> None:
    switch_on(shop_b)
    with shop_context(shop_b):
        MealMoney(shop=shop_b, date=MONDAY, amount=Decimal("9000"), created_by=staff_b).save()
    typed(baba, MONDAY, "8000")
    assert by_date(days_of(shop_a))[MONDAY].amount == Decimal("8000")
    with shop_context(shop_b), pytest.raises(ShopMismatch):
        meal_money_days(shop_a, NOV_1, NOV_30)


def test_only_the_demo_offers_a_ready_reason(settings: Settings, shop_a: Shop) -> None:
    assert days_of(shop_a).ready_void_reasons == []
    settings.DEMO_SEED = True
    assert days_of(shop_a).ready_void_reasons == ["wrong_amount"]
