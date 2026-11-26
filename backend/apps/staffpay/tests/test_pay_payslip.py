"""apps/staffpay/tests/test_pay_payslip.py — handing out a payslip (WAGE-9; 02 §12, A5): pay_payslip
(apps/staffpay/services/payment.py).

    2 Dec, Baba pays November, approved:
        Asha    152,000  Taslimu, her signature drawn        → Amelipwa taslimu na Baba
        Baraka  148,000  M-Pesa, "qk7h 2m9xpl"                → kept as QK7H2M9XPL
        Juma          0  he took more before payday than he earned → nothing to hand over, no Lipa

The whole amount, at once (Jack: A); in cash only with the worker's signature, by M-Pesa or a bank only with a number
not counted already; never one's own; once. The payslips are written straight in, as approving them is WAGE-3's and is
proven there. The amounts are made up: the repo is public (rule 10).
"""

import datetime as dt
import hashlib
import uuid
from collections.abc import Callable
from decimal import Decimal
from typing import Any

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from pytest_django import Settings

from apps.control.models import Attachment, AttachmentKind
from apps.core.permissions import Permission, RoleTemplate
from apps.core.tenancy import ShopMismatch, shop_context
from apps.people.models import PermissionGrant, StaffMember
from apps.people.services import end_permission, grant_permission, hire_again, mark_left, suspend
from apps.shops.models import Shop, Side
from apps.staffpay.models import NoSignature, PaymentMethod, Payslip, PayslipPayment
from apps.staffpay.services import PAYS, pay_payslip
from apps.staffpay.tests.days import job
from tests.concurrency import in_another_transaction, wait_until_someone_waits_for_me

pytestmark = pytest.mark.django_db

GiveRole = Callable[[StaffMember, RoleTemplate, Side | None], None]

NOVEMBER = dt.date(2026, 11, 1)
CASH, MOBILE, BANK = PaymentMethod.CASH, PaymentMethod.MOBILE_MONEY, PaymentMethod.BANK
# A made-up drawing: a JPEG's first bytes, then words that are no picture.
DRAWING = b"\xff\xd8\xff\xe0" + b"Asha's signature, made up " * 20


@pytest.fixture
def baba(shop_a: Shop, give_role: GiveRole) -> StaffMember:
    # The owner: every key.
    staff = job(shop_a, "Baba")
    give_role(staff, RoleTemplate.OWNER, None)
    return staff


@pytest.fixture
def meneja(shop_a: Shop, give_role: GiveRole) -> StaffMember:
    # A manager: `pay.run` from his role, and the two keys of pay the owner handed him. Not `pay.approve`: he hands out
    # what Baba approved, and approves nothing himself.
    staff = job(shop_a, "Meneja")
    give_role(staff, RoleTemplate.MANAGER, None)
    with shop_context(shop_a):
        for key in (Permission.SETTINGS_MANAGE, Permission.STAFF_MANAGE):
            grant_permission(staff, key, side=None, by=None)
    return staff


def slip(staff: StaffMember, by: StaffMember, total: str = "152000.00") -> Payslip:
    # The worker's November as an approval keeps it, approved alone (no run), as the payment reads no more of it.
    with shop_context(staff.shop_id):
        return Payslip.objects.create(
            shop_id=staff.shop_id, staff=staff, month=NOVEMBER, total=Decimal(total), created_by=by
        )


@pytest.fixture
def asha(shop_a: Shop, baba: StaffMember) -> Payslip:
    return slip(job(shop_a, "Asha"), baba)


def in_cash(payslip: Payslip, by: StaffMember, **other: Any) -> PayslipPayment:
    sent: dict[str, Any] = {"payment_id": uuid.uuid7(), "method": CASH, "signature_id": uuid.uuid7()}
    with shop_context(payslip.shop_id):
        return pay_payslip(payslip, **(sent | {"signature": DRAWING} | other), by=by)


def by_number(payslip: Payslip, by: StaffMember, number: str = "QK7H2M9XPL", **other: Any) -> PayslipPayment:
    sent: dict[str, Any] = {"payment_id": uuid.uuid7(), "method": MOBILE, "reference": number}
    with shop_context(payslip.shop_id):
        return pay_payslip(payslip, **(sent | other), by=by)


def payments(payslip: Payslip) -> list[PayslipPayment]:
    with shop_context(payslip.shop_id):
        return list(PayslipPayment.objects.filter(payslip=payslip).order_by("created_at"))


def signatures(shop: Shop) -> list[Attachment]:
    with shop_context(shop):
        return list(Attachment.objects.filter(kind=AttachmentKind.SIGNATURE))


def code_of(refusal: pytest.ExceptionInfo[ValidationError]) -> str:
    # The one code a refusal carries, whether said of the whole payment or beside a box.
    error = refusal.value
    if hasattr(error, "error_dict"):
        [(_, [inner])] = error.error_dict.items()
        return str(inner.code)
    return str(error.code)


def test_baba_pays_asha_in_cash_with_her_signature(shop_a: Shop, baba: StaffMember, asha: Payslip) -> None:
    # The whole of it, by Baba, now; and her signature pinned to the payment, its file kept as drawn.
    row = in_cash(asha, baba)
    assert (row.amount, row.method, row.reference, row.no_signature) == (Decimal("152000.00"), CASH, "", "")
    assert (row.created_by_id, row.staff_id, row.voided_at) == (baba.pk, asha.staff_id, None)
    [signed] = signatures(shop_a)
    assert (signed.subject_type, signed.subject_id, signed.created_by_id) == ("payslip_payment", row.pk, baba.pk)
    assert signed.sha256 == hashlib.sha256(DRAWING).hexdigest()
    with shop_context(shop_a), signed.file.open("rb") as kept:
        assert kept.read() == DRAWING


@pytest.mark.parametrize("method", [MOBILE, BANK])
def test_by_mpesa_or_a_bank_with_its_number(baba: StaffMember, asha: Payslip, method: PaymentMethod) -> None:
    # The number as the owner finds it on his statement: spaces and small letters typed are one number with it.
    row = by_number(asha, baba, " qk7h 2m9xpl ", method=method)
    assert (row.method, row.reference, row.amount) == (method, "QK7H2M9XPL", Decimal("152000.00"))
    assert signatures(asha.shop) == []


def test_cash_needs_the_signature(baba: StaffMember, asha: Payslip) -> None:
    # A payment marked by one person alone proves nothing (Jack: A): Nimemlipa waits for her drawing.
    with pytest.raises(ValidationError) as refused:
        in_cash(asha, baba, signature_id=None, signature=None)
    assert code_of(refused) == "payment.signature_missing"
    assert payments(asha) == []


@pytest.mark.parametrize(
    ("number", "code"),
    [
        ("", "payment.reference_missing"),
        ("   ", "payment.reference_missing"),
        ("QK7H#2M9", "payment.reference_invalid"),
    ],
)
def test_mpesa_needs_a_number(baba: StaffMember, asha: Payslip, number: str, code: str) -> None:
    # Said beside the number's box, where it is typed.
    with pytest.raises(ValidationError) as refused:
        by_number(asha, baba, number)
    assert list(refused.value.error_dict) == ["reference"]
    assert code_of(refused) == code
    assert payments(asha) == []


def test_a_number_proves_one_payment(shop_a: Shop, baba: StaffMember, asha: Payslip) -> None:
    # The same code typed on Baraka's payslip would let one payment stand for two (01 §7.5). By a bank it is another
    # bank's number, and once Asha's is crossed out, the number is free again.
    baraka = slip(job(shop_a, "Baraka"), baba, "148000.00")
    first = by_number(asha, baba)
    with pytest.raises(ValidationError) as refused:
        by_number(baraka, baba, "qk7h2m9xpl")
    assert list(refused.value.error_dict) == ["reference"]
    assert code_of(refused) == "payment.reference_used"
    by_number(baraka, baba, method=BANK)
    with shop_context(shop_a):
        PayslipPayment.objects.filter(pk=first.pk).update(
            voided_at=first.created_at, voided_by=baba, void_reason="Kosa"
        )
    by_number(asha, baba, method=MOBILE)


@pytest.mark.parametrize("total", ["0.00", "-18000.00"])
def test_a_payslip_that_pays_nothing_has_no_payment(baba: StaffMember, shop_a: Shop, total: str) -> None:
    # Juma took more before payday than he earned: he is paid 0 (WAGE-3), so there is nothing to hand over or sign for.
    juma = slip(job(shop_a, "Juma"), baba, total)
    with pytest.raises(ValidationError) as refused:
        in_cash(juma, baba)
    assert code_of(refused) == "payment.nothing_to_pay"
    assert payments(juma) == [] and signatures(shop_a) == []


def test_a_payslip_is_paid_once(baba: StaffMember, asha: Payslip) -> None:
    # Paid in cash; marking it paid again by M-Pesa is refused, and her one signature stays the only one.
    in_cash(asha, baba)
    with pytest.raises(ValidationError) as refused:
        by_number(asha, baba)
    assert code_of(refused) == "payment.already_paid"
    assert len(payments(asha)) == 1 and len(signatures(asha.shop)) == 1


def test_sent_twice_is_one_payment(baba: StaffMember, asha: Payslip) -> None:
    # The answer was lost on the way and the phone sent it again: the same payment, not a second, nor a refusal.
    payment_id, signature_id = uuid.uuid7(), uuid.uuid7()
    first = in_cash(asha, baba, payment_id=payment_id, signature_id=signature_id)
    again = in_cash(asha, baba, payment_id=payment_id, signature_id=signature_id)
    assert again.pk == first.pk
    assert len(payments(asha)) == 1 and len(signatures(asha.shop)) == 1


def test_a_drawing_that_is_no_picture_keeps_nothing(baba: StaffMember, asha: Payslip) -> None:
    # The signature is refused, and the payment with it: cash is never kept unsigned.
    with pytest.raises(ValidationError) as refused:
        in_cash(asha, baba, signature=b"no picture at all")
    assert code_of(refused) == "attachment.not_an_image"
    assert payments(asha) == [] and signatures(asha.shop) == []


def test_nobody_pays_their_own(shop_a: Shop, baba: StaffMember, meneja: StaffMember) -> None:
    # 02 A5: Meneja holds every key it takes, and still may not mark his own November paid.
    own = slip(meneja, baba, "250000.00")
    with pytest.raises(ValidationError) as refused:
        by_number(own, meneja)
    assert code_of(refused) == "payment.own"
    assert payments(own) == []


def test_ones_own_is_the_persons_not_the_jobs(shop_a: Shop, give_role: GiveRole, baba: StaffMember) -> None:
    # Baraka sold until the 14th and came back on the 16th as a manager (PPL-11): one person, two jobs. His old job's
    # November is his all the same.
    old = job(shop_a, "Baraka")
    with shop_context(shop_a):
        mark_left(old, left_on=dt.date(2026, 11, 14), by=None, reason="Ameacha kazi")
        new = hire_again(old, display_name="Baraka", started_on=dt.date(2026, 11, 16), by=None)
    give_role(new, RoleTemplate.OWNER, None)
    leaver = slip(old, baba, "62000.00")
    with pytest.raises(ValidationError) as refused:
        by_number(leaver, new)
    assert code_of(refused) == "payment.own"


@pytest.mark.parametrize("missing", PAYS)
def test_without_each_key_nobody_pays(
    shop_a: Shop, give_role: GiveRole, baba: StaffMember, asha: Payslip, missing: Permission
) -> None:
    # `pay.run` and the two keys of pay, on the whole shop; `pay.approve` isn't asked, as Meneja hands out what Baba
    # approved. A seller holds none of the three.
    neema = job(shop_a, "Neema")
    give_role(neema, RoleTemplate.SELLER, None)
    with shop_context(shop_a):
        for key in PAYS:
            if key != missing:
                grant_permission(neema, key, side=None, by=None)
    with pytest.raises(PermissionDenied):
        by_number(asha, neema)
    assert payments(asha) == []
    with shop_context(shop_a):
        grant_permission(neema, missing, side=None, by=None)
    assert by_number(asha, neema).created_by_id == neema.pk


def test_pays_needs_no_approval_key(meneja: StaffMember, asha: Payslip) -> None:
    # Written out, so a change to who hands out pay is a change to this test too.
    assert PAYS == (Permission.PAY_RUN, Permission.SETTINGS_MANAGE, Permission.STAFF_MANAGE)
    assert by_number(asha, meneja).created_by_id == meneja.pk


def test_a_key_on_one_side_pays_nothing(shop_a: Shop, side_a: Side, asha: Payslip) -> None:
    # A worker's pay is the whole shop's: the three keys on the Drugs side alone hand out nothing.
    neema = job(shop_a, "Neema")
    with shop_context(shop_a):
        for key in PAYS:
            grant_permission(neema, key, side=side_a, by=None)
    with pytest.raises(PermissionDenied):
        by_number(asha, neema)


def test_on_the_demo_cash_keeps_no_signature(settings: Settings, baba: StaffMember, asha: Payslip) -> None:
    # Every demo visitor is the same Meneja (OPS-3), so a signature kept would show to the next one (Jack, ATT-3 and
    # PPL-9: none is kept). The visitor draws; the app sends nothing; the payment says why it has none.
    settings.DEMO_SEED = True
    with pytest.raises(ValidationError) as refused:
        in_cash(asha, baba)
    assert code_of(refused) == "demo.no_signature"
    row = in_cash(asha, baba, signature_id=None, signature=None)
    assert row.no_signature == NoSignature.DEMO
    assert signatures(asha.shop) == []


def test_a_person_of_another_shop_is_a_bug(asha: Payslip, staff_b: StaffMember) -> None:
    # T1: the route finds both in the one shop open, so another shop's person here is our code's mistake.
    with pytest.raises(ShopMismatch, match="pay_payslip"):
        by_number(asha, staff_b)


def test_what_no_route_sends_is_a_bug(baba: StaffMember, asha: Payslip) -> None:
    # Each route sends one way of paying: a number with cash, or a signature with M-Pesa, is our code's mistake.
    with pytest.raises(ValueError, match="never a transaction number"):
        in_cash(asha, baba, reference="QK7H2M9XPL")
    with pytest.raises(ValueError, match="Only cash"):
        by_number(asha, baba, signature_id=uuid.uuid7(), signature=DRAWING)
    with pytest.raises(ValueError, match="with its id"):
        in_cash(asha, baba, signature_id=None)


@pytest.mark.django_db(transaction=True)
def test_two_people_paying_at_once_make_one_payment(baba: StaffMember, meneja: StaffMember, asha: Payslip) -> None:
    # Baba and Meneja both tap Nimemlipa for Asha. The second waits for the first's lock on her payslip, then finds it
    # paid: she is never paid twice.
    def again() -> str:
        try:
            by_number(asha, meneja, "QK7H2N4ZTR")
        except ValidationError as refusal:
            return str(refusal.code)
        return "paid"

    with shop_context(asha.shop_id), transaction.atomic():
        in_cash(asha, baba)
        thread, ended = in_another_transaction(again)
        wait_until_someone_waits_for_me()
    thread.join()
    assert ended == ["payment.already_paid"]
    assert len(payments(asha)) == 1


@pytest.mark.django_db(transaction=True)
def test_one_number_on_two_payslips_at_once(
    shop_a: Shop, baba: StaffMember, meneja: StaffMember, asha: Payslip
) -> None:
    # Baba types QK7H2M9XPL for Asha and Meneja the same for Baraka, in the same second: each holds only his own
    # payslip's lock, so both find the number free. The table's rule refuses the second, said as the same refusal.
    baraka = slip(job(shop_a, "Baraka"), baba, "148000.00")

    def same_number() -> str:
        try:
            by_number(baraka, meneja)
        except ValidationError as refusal:
            return ",".join(str(inner.code) for inner in refusal.error_dict["reference"])
        return "paid"

    with shop_context(shop_a), transaction.atomic():
        by_number(asha, baba)
        thread, ended = in_another_transaction(same_number)
        wait_until_someone_waits_for_me()
    thread.join()
    assert ended == ["payment.reference_used"]
    assert payments(baraka) == []


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("lost", ["a key", "his job"])
def test_a_key_taken_away_meanwhile_pays_nothing(
    shop_a: Shop, baba: StaffMember, meneja: StaffMember, asha: Payslip, lost: str
) -> None:
    # Baba takes a key from Meneja, or suspends him, while Meneja taps Nimemlipa: he holds it still as he starts, waits
    # for his own row, and is asked again once he has it. A payment marked by someone without the key would stand.
    with shop_context(shop_a):
        [key] = PermissionGrant.objects.filter(staff=meneja, permission=Permission.STAFF_MANAGE)

    def pays() -> str:
        try:
            by_number(asha, meneja)
        except PermissionDenied:
            return "refused"
        return "paid"

    with shop_context(shop_a), transaction.atomic():
        if lost == "a key":
            end_permission(key, reason="Baba atalipa mwenyewe", by=baba)
        else:
            suspend(meneja, reason="Uchunguzi", by=baba)
        thread, ended = in_another_transaction(pays)
        wait_until_someone_waits_for_me()
    thread.join()
    assert ended == ["refused"]
    assert payments(asha) == []
