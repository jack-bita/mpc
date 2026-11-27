"""apps/staffpay/tests/test_record_correction.py — putting right a mistake of a month already approved, in a month
still open (record_correction): WAGE-10, 02 §12, A3.

Baba approved November on 1 December. On the 3rd he finds Juma's November was 9,000 short, and adds + 9,000 to Juma's
December: "Novemba: siku ya 12/11 haikuhesabiwa". Asha was paid 5,000 too much: − 5,000 in her December.

    the one typing                               the answer
    Baba, who approves pay                       the row, with who typed it
    Meneja, a manager without pay.approve        403: a correction changes what is owed (Jack: A)
    the keys on one side alone                   403: a worker's pay is the whole shop's
    one's own, on any of one's jobs              correction.own
    one who left, whose pay is approved          correction.left_paid (Jack: A)
    a month to come                              correction.month_to_come
    a month the job didn't run in                correction.outside_job
    a worker with no daily pay that month        correction.not_paid_by_day
    a month whose pay is approved                pay.day_approved
    0, cents, or over ten million either way     correction.amount_invalid, correction.amount_too_big
    no reason                                    correction.reason_missing
    on the demo, a typed reason                  demo.ready_reasons

What the table refuses by itself is test_pay_correction.py's; what the pay makes of it, test_pay_month.py's. Months are
approved here by writing their rows, as the approval's own tests are test_approve_month.py's. The amounts are made up
(rule 10). Fake data only: the repo is public.
"""

import datetime as dt
import uuid
from collections.abc import Callable
from decimal import Decimal
from typing import Any

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from pytest_django import Settings

from apps.core.models import Change
from apps.core.permissions import Permission, RoleTemplate
from apps.core.tenancy import ShopMismatch, shop_context
from apps.people.models import PermissionGrant, StaffMember
from apps.people.services import end_permission, grant_permission, hire_again, mark_left, suspend
from apps.shops.models import Shop, Side
from apps.staffpay.models import PayCorrection, PayRate, PayRun, Payslip
from apps.staffpay.services import DEMO_CORRECTION_REASONS, ready_correction_reasons, record_correction
from apps.staffpay.tests.days import JAN_1, job
from tests.concurrency import in_another_transaction, wait_until_someone_waits_for_me

pytestmark = pytest.mark.django_db

GiveRole = Callable[[StaffMember, RoleTemplate, Side | None], None]

OCTOBER, NOVEMBER, DECEMBER, JANUARY = (
    dt.date(2026, 10, 1),
    dt.date(2026, 11, 1),
    dt.date(2026, 12, 1),
    dt.date(2027, 1, 1),
)
REASON = "Novemba: siku ya 12/11 haikuhesabiwa"


@pytest.fixture(autouse=True)
def third_of_december(monkeypatch: pytest.MonkeyPatch) -> None:
    # 10:05 on Thursday 3 December in Arusha: November is over, December runs.
    moment = dt.datetime(2026, 12, 3, 10, 5, tzinfo=dt.timezone(dt.timedelta(hours=3)))
    monkeypatch.setattr(timezone, "now", lambda: moment)


def paid_by_day(staff: StaffMember, since: dt.date = JAN_1) -> StaffMember:
    # A daily pay rate, a made-up 10,000, written past set_pay_rate, whose maker would need the keys of pay.
    with shop_context(staff.shop_id):
        PayRate(shop_id=staff.shop_id, staff=staff, daily_rate=Decimal("10000.00"), effective_from=since).save()
    return staff


@pytest.fixture
def juma(shop_a: Shop) -> StaffMember:
    # Paid by the day since January.
    return paid_by_day(job(shop_a, "Juma"))


@pytest.fixture
def baba(shop_a: Shop, give_role: GiveRole) -> StaffMember:
    # The owner: every key, pay.approve among them, on the whole shop, and no daily pay.
    staff = job(shop_a, "Baba")
    give_role(staff, RoleTemplate.OWNER, None)
    return staff


@pytest.fixture
def meneja(shop_a: Shop, give_role: GiveRole) -> StaffMember:
    # A manager of the whole shop: both keys of pay, money.advance too, and not pay.approve, the owner's own (03 §5.8).
    # Paid by the day too.
    staff = paid_by_day(job(shop_a, "Meneja"))
    give_role(staff, RoleTemplate.MANAGER, None)
    return staff


def correct(
    staff: StaffMember, by: StaffMember, amount: str = "9000.00", month: dt.date = DECEMBER, **more: Any
) -> PayCorrection:
    facts: dict[str, Any] = {"correction_id": uuid.uuid7(), "reason": REASON, **more}
    with shop_context(staff.shop_id):
        return record_correction(staff, month=month, amount=Decimal(amount), by=by, **facts)


def approved(shop: Shop, month: dt.date, by: StaffMember) -> None:
    # A month approved, as its row says (PayRun): what closes it for every job (is_closed).
    with shop_context(shop):
        PayRun.objects.create(shop=shop, month=month, created_by=by)


def codes_of(refused: pytest.ExceptionInfo[ValidationError]) -> dict[str, set[str]]:
    # Each box's codes, as the page shows them beside it; the whole request's under "__all__".
    return {field: {error.code or "" for error in errors} for field, errors in refused.value.error_dict.items()}


def code_of(refused: pytest.ExceptionInfo[ValidationError]) -> str | None:
    # The one code of a refusal of the whole request.
    (error,) = refused.value.error_list
    return error.code


def holding_the_three_keys(staff: StaffMember, side: Side | None = None, missing: str | None = None) -> StaffMember:
    # pay.approve and the two keys of pay, given to a job of its own, or all but one.
    with shop_context(staff.shop_id):
        for key in (Permission.PAY_APPROVE, Permission.SETTINGS_MANAGE, Permission.STAFF_MANAGE):
            if key != missing:
                grant_permission(staff, key, side=side, by=None)
    return staff


def rows_of(shop: Shop) -> int:
    with shop_context(shop):
        return PayCorrection.objects.count()


# Typing one.


def test_baba_adds_to_jumas_december(shop_a: Shop, baba: StaffMember, juma: StaffMember) -> None:
    correction_id = uuid.uuid7()
    # Any day of the month names it: kept as its first day.
    row = correct(juma, baba, month=dt.date(2026, 12, 3), correction_id=correction_id, reason=f"  {REASON} ")
    with shop_context(shop_a):
        kept = PayCorrection.objects.get(pk=correction_id)
    assert row.pk == kept.pk
    assert (kept.staff_id, kept.month, kept.amount) == (juma.pk, DECEMBER, Decimal("9000.00"))
    assert kept.created_by_id == baba.pk
    # Spaces around a reason say nothing.
    assert kept.reason == REASON
    assert kept.voided_at is None


def test_one_takes_off_too(baba: StaffMember, juma: StaffMember) -> None:
    # Paid 5,000 too much in November: − 5,000 in December.
    row = correct(juma, baba, "-5000.00", reason="Novemba: alilipwa zaidi")
    assert row.amount == Decimal("-5000.00")


def test_several_are_kept(shop_a: Shop, baba: StaffMember, juma: StaffMember) -> None:
    # Two mistakes of November, one each way: each is its own line.
    correct(juma, baba)
    correct(juma, baba, "-2000.00", reason="Novemba: faini mara mbili")
    assert rows_of(shop_a) == 2


def test_a_month_still_open_before_today_takes_one(shop_a: Shop, baba: StaffMember, juma: StaffMember) -> None:
    # 3 December, November not approved yet: a mistake of October may go in November, paid the sooner (Claude's
    # default, in the plan Jack approved). October approved, so its own pay takes none.
    approved(shop_a, OCTOBER, baba)
    row = correct(juma, baba, month=NOVEMBER, reason="Oktoba: siku ya 7/10 haikuhesabiwa")
    assert row.month == NOVEMBER


def test_a_month_to_come_takes_none(baba: StaffMember, juma: StaffMember) -> None:
    # January has no pay yet: a slip of the month.
    with pytest.raises(ValidationError) as refused:
        correct(juma, baba, month=JANUARY)
    assert code_of(refused) == "correction.month_to_come"


def test_an_approved_month_takes_none(shop_a: Shop, baba: StaffMember, juma: StaffMember) -> None:
    # November is approved: its payslips are final (A3), so the mistake goes in December, never in November.
    approved(shop_a, NOVEMBER, baba)
    with pytest.raises(ValidationError) as refused:
        correct(juma, baba, month=NOVEMBER)
    assert code_of(refused) == "pay.day_approved"
    # Nor one before it: months are approved in order, so October is closed with it.
    with pytest.raises(ValidationError) as refused:
        correct(juma, baba, month=OCTOBER)
    assert code_of(refused) == "pay.day_approved"
    correct(juma, baba)
    assert rows_of(shop_a) == 1


def test_only_a_month_the_job_ran_in(shop_a: Shop, baba: StaffMember) -> None:
    # Amani started on 10 December: his November is no pay of his.
    with shop_context(shop_a):
        amani = job(shop_a, "Amani")
        StaffMember.objects.filter(pk=amani.pk).update(started_on=dt.date(2026, 12, 10))
        amani.refresh_from_db()
    paid_by_day(amani, dt.date(2026, 12, 10))
    with pytest.raises(ValidationError) as refused:
        correct(amani, baba, month=NOVEMBER)
    assert code_of(refused) == "correction.outside_job"
    correct(amani, baba)
    assert rows_of(shop_a) == 1


def test_only_a_worker_paid_by_the_day_that_month(shop_a: Shop, baba: StaffMember) -> None:
    # The owner has no daily pay, so no pay to put it in, corrected by a second owner. Hamisi's first rate starts on 1
    # December: his December takes one, his November none.
    hamisi = paid_by_day(job(shop_a, "Hamisi"), DECEMBER)
    other = holding_the_three_keys(job(shop_a, "Mjomba"))
    with pytest.raises(ValidationError) as refused:
        correct(baba, other)
    assert code_of(refused) == "correction.not_paid_by_day"
    with pytest.raises(ValidationError) as refused:
        correct(hamisi, other, month=NOVEMBER)
    assert code_of(refused) == "correction.not_paid_by_day"
    correct(hamisi, other)
    assert rows_of(shop_a) == 1


@pytest.fixture
def neema(shop_a: Shop, baba: StaffMember) -> StaffMember:
    # Neema left on 25 November and was approved alone that evening: her payslip of November, with no run.
    staff = paid_by_day(job(shop_a, "Neema"))
    with shop_context(shop_a):
        staff = mark_left(staff, left_on=dt.date(2026, 11, 25), by=None, reason="Amehama")
        Payslip.objects.create(shop=shop_a, staff=staff, month=NOVEMBER, total=Decimal("10000.00"), created_by=baba)
    return staff


@pytest.mark.parametrize("month", [NOVEMBER, DECEMBER])
def test_one_who_left_and_was_paid_takes_none(baba: StaffMember, neema: StaffMember, month: dt.date) -> None:
    # Jack: A. No later pay of Neema's will be made, so whatever month is asked, the system says why, and Baba pays her
    # by hand: the same words for her November, closed, and her December, which she never worked.
    with pytest.raises(ValidationError) as refused:
        correct(neema, baba, month=month)
    assert code_of(refused) == "correction.left_paid"


def test_one_who_left_and_is_not_paid_yet_takes_one(shop_a: Shop, baba: StaffMember, juma: StaffMember) -> None:
    # Juma left on 30 November, his pay not approved yet: his November still takes one, as it is still open. His
    # December, which he never worked, takes none.
    with shop_context(shop_a):
        juma = mark_left(juma, left_on=dt.date(2026, 11, 30), by=None, reason="Amehama")
    correct(juma, baba, month=NOVEMBER)
    with pytest.raises(ValidationError) as refused:
        correct(juma, baba)
    assert code_of(refused) == "correction.outside_job"
    assert rows_of(shop_a) == 1


def test_one_suspended_takes_one(baba: StaffMember, juma: StaffMember, shop_a: Shop) -> None:
    # Suspended this morning: what he was owed in November is owed all the same.
    with shop_context(shop_a):
        suspend(juma, by=None, reason="Uchunguzi")
    correct(juma, baba)
    assert rows_of(shop_a) == 1


@pytest.mark.parametrize("amount", ["0.00", "9000.50", "-9000.50"])
def test_a_correction_is_whole_shillings_and_never_nothing(baba: StaffMember, juma: StaffMember, amount: str) -> None:
    with pytest.raises(ValidationError) as refused:
        correct(juma, baba, amount)
    assert codes_of(refused) == {"amount": {"correction.amount_invalid"}}


@pytest.mark.parametrize("amount", ["10000001.00", "-10000001.00"])
def test_an_amount_with_zeros_too_many_is_refused(
    shop_a: Shop, baba: StaffMember, juma: StaffMember, amount: str
) -> None:
    # Ten million is more than any month's pay: a slip of the zeros, either way. Ten million itself is taken.
    with pytest.raises(ValidationError) as refused:
        correct(juma, baba, amount)
    assert codes_of(refused) == {"amount": {"correction.amount_too_big"}}
    correct(juma, baba, "10000000.00")
    correct(juma, baba, "-10000000.00")
    assert rows_of(shop_a) == 2


@pytest.mark.parametrize("reason", ["", "   "])
def test_a_correction_says_why(baba: StaffMember, juma: StaffMember, reason: str) -> None:
    with pytest.raises(ValidationError) as refused:
        correct(juma, baba, reason=reason)
    assert codes_of(refused) == {"reason": {"correction.reason_missing"}}


def test_every_mistake_of_the_boxes_comes_back_at_once(baba: StaffMember, juma: StaffMember) -> None:
    # Two wrong boxes: each said beside its own, so a person mends both in one go (ADR-0040).
    with pytest.raises(ValidationError) as refused:
        correct(juma, baba, "0.00", reason="")
    assert codes_of(refused) == {"amount": {"correction.amount_invalid"}, "reason": {"correction.reason_missing"}}


def test_a_reason_too_long_is_refused(baba: StaffMember, juma: StaffMember) -> None:
    with pytest.raises(ValidationError) as refused:
        correct(juma, baba, reason="u" * 201)
    assert set(codes_of(refused)) == {"reason"}


def test_an_id_another_row_holds_never_writes_over_it(baba: StaffMember, juma: StaffMember, shop_a: Shop) -> None:
    # The route answers a request sent twice with the row it made (CreateOnceMixin); the service itself never turns a
    # second call with the same id into a change of the first (03 §5.4).
    row = correct(juma, baba)
    with pytest.raises(ValidationError):
        correct(juma, baba, "90000.00", correction_id=row.pk)
    with shop_context(shop_a):
        assert PayCorrection.objects.get().amount == Decimal("9000.00")


def test_a_correction_tells_no_laptop(shop_a: Shop, baba: StaffMember, juma: StaffMember) -> None:
    # A worker's pay never sits on a shared device (03 §6.1): typing one writes no line in the change log, so no pull
    # ever carries it.
    with shop_context(shop_a):
        lines = Change.objects.count()
    correct(juma, baba)
    with shop_context(shop_a):
        assert Change.objects.count() == lines


def test_the_job_is_of_the_same_shop(shop_a: Shop, shop_b: Shop, staff_b: StaffMember, juma: StaffMember) -> None:
    # A person of another shop here is a bug in the calling code (T1), never a person's mistake: the route finds both
    # in the one shop open.
    with shop_context(shop_a), pytest.raises(ShopMismatch):
        record_correction(
            juma, correction_id=uuid.uuid7(), month=DECEMBER, amount=Decimal("9000"), reason=REASON, by=staff_b
        )
    assert rows_of(shop_a) == 0


# Who may.


def test_a_manager_without_the_approvals_key_types_none(meneja: StaffMember, juma: StaffMember, shop_a: Shop) -> None:
    # Jack: A. Meneja types advances, money that left the drawer; a correction changes what is owed with no cash to show
    # for it, so only whoever approves pay types one.
    with pytest.raises(PermissionDenied):
        correct(juma, meneja)
    assert rows_of(shop_a) == 0


@pytest.mark.parametrize("missing", [Permission.PAY_APPROVE, Permission.SETTINGS_MANAGE, Permission.STAFF_MANAGE])
def test_each_of_the_three_keys_is_asked(shop_a: Shop, juma: StaffMember, missing: Permission) -> None:
    # pay.approve, and the two keys of pay, as nobody corrects what they may not read (02 §5): two of the three open
    # nothing.
    other = holding_the_three_keys(job(shop_a, "Mjomba"), missing=missing)
    with pytest.raises(PermissionDenied):
        correct(juma, other)
    assert rows_of(shop_a) == 0


def test_the_keys_on_one_side_type_nothing(shop_a: Shop, side_a: Side, juma: StaffMember) -> None:
    # A worker's pay is the whole shop's: the three keys given on Dawa alone open nothing of it (02 §5).
    other = holding_the_three_keys(job(shop_a, "Mjomba"), side=side_a)
    with pytest.raises(PermissionDenied):
        correct(juma, other)


def test_nobody_corrects_their_own(shop_a: Shop, baba: StaffMember, give_role: GiveRole) -> None:
    # Jack: A. Mjomba, who approves pay while Baba is away, is paid by the day too: he never raises his own.
    mjomba = paid_by_day(job(shop_a, "Mjomba"))
    give_role(mjomba, RoleTemplate.OWNER, None)
    with pytest.raises(ValidationError) as refused:
        correct(mjomba, mjomba)
    assert code_of(refused) == "correction.own"
    correct(mjomba, baba)
    assert rows_of(shop_a) == 1


def test_nor_on_a_job_they_held_before(shop_a: Shop, baba: StaffMember, give_role: GiveRole) -> None:
    # By the person, not the job: Mjomba left in October and was hired again on 1 November (PPL-11). His old job's pay
    # is his own all the same.
    with shop_context(shop_a):
        old = paid_by_day(job(shop_a, "Mjomba"))
        old = mark_left(old, left_on=dt.date(2026, 10, 31), by=None, reason="Amehama")
        new = hire_again(old, display_name="Mjomba", started_on=NOVEMBER, by=None)
    give_role(new, RoleTemplate.OWNER, None)
    with pytest.raises(ValidationError) as refused:
        correct(old, new, month=OCTOBER)
    assert code_of(refused) == "correction.own"


def test_one_suspended_types_nothing(shop_a: Shop, baba: StaffMember, juma: StaffMember) -> None:
    # Baba suspended a second owner this morning, in a tab still open from before: no key counts (X2), read afresh.
    mjomba = holding_the_three_keys(job(shop_a, "Mjomba"))
    with shop_context(shop_a):
        suspend(mjomba, by=None, reason="Uchunguzi")
    with pytest.raises(PermissionDenied):
        correct(juma, mjomba)


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("lost", ["a key", "his job"])
def test_a_key_taken_away_meanwhile_corrects_nothing(
    shop_a: Shop, baba: StaffMember, juma: StaffMember, lost: str
) -> None:
    # Baba takes a key from Mjomba, or suspends him, while Mjomba taps Hifadhi: he holds it still as he starts, waits
    # for his own row, and is asked again once he has it. A correction typed by someone without the key would stand.
    mjomba = holding_the_three_keys(job(shop_a, "Mjomba"))
    with shop_context(shop_a):
        [key] = PermissionGrant.objects.filter(staff=mjomba, permission=Permission.STAFF_MANAGE)

    def corrects() -> str:
        try:
            correct(juma, mjomba)
        except PermissionDenied:
            return "refused"
        return "corrected"

    with shop_context(shop_a), transaction.atomic():
        if lost == "a key":
            end_permission(key, reason="Baba atarekebisha mwenyewe", by=baba)
        else:
            suspend(mjomba, reason="Uchunguzi", by=baba)
        thread, ended = in_another_transaction(corrects)
        wait_until_someone_waits_for_me()
    thread.join()
    assert ended == ["refused"]
    assert rows_of(shop_a) == 0


# The demo.


def test_on_the_demo_a_reason_is_a_ready_one(
    settings: Settings, shop_a: Shop, baba: StaffMember, juma: StaffMember
) -> None:
    # Every visitor is the same Meneja, so a reason typed would show to the next: only the ready ones, kept as their
    # codes, which the page says in words.
    settings.DEMO_SEED = True
    with pytest.raises(ValidationError) as refused:
        correct(juma, baba)
    assert codes_of(refused) == {"reason": {"demo.ready_reasons"}}
    assert ready_correction_reasons() == list(DEMO_CORRECTION_REASONS) == ["day_not_counted", "paid_too_much"]
    for reason in DEMO_CORRECTION_REASONS:
        correct(juma, baba, reason=reason)
    assert rows_of(shop_a) == 2


def test_anywhere_else_there_is_no_ready_reason(settings: Settings) -> None:
    settings.DEMO_SEED = False
    assert ready_correction_reasons() == []
