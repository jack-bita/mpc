"""apps/staffpay/tests/test_payment_routes.py — Lipa and Batilisha as the office pages call them (WAGE-9; 03 §5.10).

    POST /api/v1/staffpay/payslips/<payslip>/pay/                      {id, method, reference}   by M-Pesa or a bank
    PUT  /api/v1/staffpay/payslips/<payslip>/pay-cash/?id=…&signature=…   body: the drawing     in cash
    POST /api/v1/staffpay/payslip-payments/<payment>/void/              {reason}                  crossed out
    GET  /api/v1/staffpay/pay/?month=2026-11                            who is paid, Bado kulipa
    GET  /api/v1/control/attachments/<signature>/file/                  the signature, with the two keys of pay

Each answers the payment as the payslip's foot shows it. Thin: what may be paid and how is pay_payslip's, proven in
test_pay_payslip.py; here, what each route takes, what it answers, and who reaches it. The payslips are written straight
in, as approving them is WAGE-3's. The amounts are made up: the repo is public (rule 10).
"""

import datetime as dt
import uuid
from collections.abc import Callable
from decimal import Decimal
from typing import Any
from urllib.parse import urlencode

import pytest
from rest_framework.test import APIClient

from apps.core.permissions import Permission, RoleTemplate
from apps.core.tenancy import shop_context
from apps.people.models import StaffMember
from apps.people.services import grant_permission
from apps.shops.models import Shop, Side
from apps.staffpay.models import PaymentMethod, PayRun, Payslip, PayslipPayment
from apps.staffpay.tests.days import job

pytestmark = pytest.mark.django_db

GiveRole = Callable[[StaffMember, RoleTemplate, Side | None], None]

NOVEMBER = dt.date(2026, 11, 1)
PAY = "/api/v1/staffpay/pay/"
DRAWING = b"\xff\xd8\xff\xe0" + b"Asha's signature, made up " * 20


def client_for(staff: StaffMember) -> APIClient:
    # The way the office screens call: logged in as this person, at their shop (backend/conftest.py).
    client = APIClient()
    client.force_authenticate(user=staff.user, token=staff)  # type: ignore[arg-type]
    return client


def by_number(payslip: uuid.UUID) -> str:
    return f"/api/v1/staffpay/payslips/{payslip}/pay/"


def in_cash(payslip: uuid.UUID, **asked: object) -> str:
    return f"/api/v1/staffpay/payslips/{payslip}/pay-cash/?{urlencode(asked)}"


def void(payment: uuid.UUID) -> str:
    return f"/api/v1/staffpay/payslip-payments/{payment}/void/"


def signature_file(attachment: str) -> str:
    return f"/api/v1/control/attachments/{attachment}/file/"


@pytest.fixture
def asha(shop_a: Shop, staff_a: StaffMember) -> Payslip:
    # Asha's November, 152,000, approved with the month by the owner (staff_a, staff_client_a's person).
    with shop_context(shop_a):
        run = PayRun.objects.create(shop=shop_a, month=NOVEMBER, created_by=staff_a)
        return Payslip.objects.create(
            shop=shop_a,
            staff=job(shop_a, "Asha"),
            month=NOVEMBER,
            pay_run=run,
            total=Decimal("152000.00"),
            created_by=staff_a,
        )


def mpesa(client: APIClient, payslip: Payslip, **other: Any) -> Any:
    sent = {"id": str(uuid.uuid7()), "method": "mobile_money", "reference": "QK7H2M9XPL"} | other
    return client.post(by_number(payslip.pk), sent, format="json")


def cash(client: APIClient, payslip: Payslip, content: bytes = DRAWING, **asked: Any) -> Any:
    ids = {"id": uuid.uuid7(), "signature": uuid.uuid7()} | asked
    return client.put(in_cash(payslip.pk, **ids), data=content, content_type="image/jpeg")


def code_of(answer: Any) -> tuple[int, str]:
    return answer.status_code, answer.json()["code"]


def test_paid_by_mpesa_as_the_sheet_sends_it(staff_client_a: APIClient, staff_a: StaffMember, asha: Payslip) -> None:
    # The payment as the payslip's foot shows it, its number as the owner's statement has it.
    sent = str(uuid.uuid7())
    answer = mpesa(staff_client_a, asha, id=sent, reference="qk7h 2m9xpl")
    assert answer.status_code == 200
    body = answer.json()
    assert {key: body[key] for key in ("id", "method", "reference", "amount", "by", "signature", "voided")} == {
        "id": sent,
        "method": "mobile_money",
        "reference": "QK7H2M9XPL",
        "amount": "152000.00",
        "by": staff_a.display_name,
        "signature": None,
        "voided": None,
    }


def test_paid_in_cash_with_the_drawing_as_its_body(staff_client_a: APIClient, shop_a: Shop, asha: Payslip) -> None:
    # The drawing kept as the signature the answer names, and opened by whoever sees the pay: the bytes as drawn.
    signature = uuid.uuid7()
    answer = cash(staff_client_a, asha, signature=signature)
    assert answer.status_code == 200
    assert (answer.json()["method"], answer.json()["signature"]) == ("cash", str(signature))
    opened = staff_client_a.get(signature_file(str(signature)))
    assert opened.status_code == 200
    assert opened.getvalue() == DRAWING


def test_sent_twice_answers_the_same_payment(staff_client_a: APIClient, asha: Payslip) -> None:
    # The answer was lost and the phone sent it again: the same payment, in both ways of paying.
    payment, signature = uuid.uuid7(), uuid.uuid7()
    first = cash(staff_client_a, asha, id=payment, signature=signature)
    again = cash(staff_client_a, asha, id=payment, signature=signature)
    assert again.status_code == 200
    assert again.json() == first.json()
    with shop_context(asha.shop_id):
        assert PayslipPayment.objects.count() == 1


@pytest.mark.parametrize(
    ("reference", "code"),
    [("", "payment.reference_missing"), ("QK7H#2M9", "payment.reference_invalid")],
)
def test_a_number_refused_beside_its_box(staff_client_a: APIClient, asha: Payslip, reference: str, code: str) -> None:
    answer = mpesa(staff_client_a, asha, reference=reference)
    assert answer.status_code == 400
    assert answer.json()["fields"] == {"reference": [code]}


def test_cash_by_the_json_route_has_no_signature(staff_client_a: APIClient, asha: Payslip) -> None:
    # Elsewhere than on the demo, cash comes with its drawing; one sent as JSON is refused, and keeps nothing.
    answer = mpesa(staff_client_a, asha, method="cash", reference="")
    assert code_of(answer) == (400, "payment.signature_missing")


def test_what_the_sheet_never_sends_is_refused(staff_client_a: APIClient, asha: Payslip) -> None:
    # A number with cash; an id that is no UUIDv7; a way of paying nobody has; a number past 30 characters.
    with_cash = mpesa(staff_client_a, asha, method="cash")
    assert with_cash.json()["fields"] == {"reference": ["invalid"]}
    wrong = mpesa(staff_client_a, asha, id=str(uuid.uuid4()), method="hundi", reference="Q" * 31)
    assert set(wrong.json()["fields"]) == {"id", "method", "reference"}
    no_ids = staff_client_a.put(in_cash(asha.pk), data=DRAWING, content_type="image/jpeg")
    assert set(no_ids.json()["fields"]) == {"id", "signature"}


def test_a_drawing_with_no_length_is_asked_again(staff_client_a: APIClient, asha: Payslip) -> None:
    # As a laptop's photo: a body that says no length is never read, and the phone is told to send it again.
    ids = {"id": uuid.uuid7(), "signature": uuid.uuid7()}
    answer = staff_client_a.put(in_cash(asha.pk, **ids), data=DRAWING, content_type="image/jpeg", CONTENT_LENGTH="")
    assert code_of(answer) == (411, "attachment.length_required")


def test_the_month_says_who_is_paid(
    staff_client_a: APIClient, staff_a: StaffMember, shop_a: Shop, asha: Payslip
) -> None:
    # Mishahara: Bado kulipa, and on Asha's line her payslip, her payment and nothing left to hand her.
    before = staff_client_a.get(PAY, {"month": "2026-11"}).json()
    assert before["still_to_pay"] == "152000.00"
    [line] = before["workers"]
    assert (line["payslip"], line["payments"], line["to_hand_out"], line["own"]) == (
        str(asha.pk),
        [],
        "152000.00",
        False,
    )
    made = mpesa(staff_client_a, asha).json()
    after = staff_client_a.get(PAY, {"month": "2026-11"}).json()
    assert after["still_to_pay"] == "0.00"
    assert after["workers"][0]["payments"] == [made]
    one = staff_client_a.get(f"{PAY}{asha.staff_id}/", {"month": "2026-11"}).json()
    assert (one["worker"]["payments"], one["void_reasons"]) == ([made], [])


def test_ones_own_line_says_so(staff_client_a: APIClient, staff_a: StaffMember, shop_a: Shop) -> None:
    # The owner's own payslip, approved by someone else: `own`, so the page offers him no Lipa on it.
    with shop_context(shop_a):
        meneja = job(shop_a, "Meneja")
        Payslip.objects.create(shop=shop_a, staff=staff_a, month=NOVEMBER, total=Decimal("1000.00"), created_by=meneja)
    [line] = staff_client_a.get(PAY, {"month": "2026-11"}).json()["workers"]
    assert line["own"] is True


def test_a_payment_crossed_out_as_the_sheet_sends_it(
    staff_client_a: APIClient, staff_a: StaffMember, asha: Payslip
) -> None:
    made = mpesa(staff_client_a, asha).json()
    answer = staff_client_a.post(void(made["id"]), {"reason": "Nilibonyeza mfanyakazi mwingine"}, format="json")
    assert answer.status_code == 200
    voided = answer.json()["voided"]
    assert (voided["by"], voided["reason"]) == (staff_a.display_name, "Nilibonyeza mfanyakazi mwingine")
    # Sent again, its answer lost: the same stamp, not a second one.
    again = staff_client_a.post(void(made["id"]), {"reason": "Nilibonyeza mfanyakazi mwingine"}, format="json")
    assert (again.status_code, again.json()["voided"]) == (200, voided)


def test_a_crossing_out_says_why(staff_client_a: APIClient, asha: Payslip) -> None:
    made = mpesa(staff_client_a, asha).json()
    answer = staff_client_a.post(void(made["id"]), {"reason": "  "}, format="json")
    assert answer.status_code == 400
    assert answer.json()["fields"] == {"reason": ["payment.reason_missing"]}


def test_another_shops_payslip_or_payment_is_not_found(
    staff_client_a: APIClient, shop_b: Shop, staff_b: StaffMember
) -> None:
    # Shop B's payslip and payment, asked by shop A's owner: "not found", as an id no shop has (03 §5.4).
    with shop_context(shop_b):
        slip = Payslip.objects.create(
            shop=shop_b, staff=job(shop_b, "Jirani"), month=NOVEMBER, total=Decimal("5000.00"), created_by=staff_b
        )
        made = PayslipPayment.objects.create(
            shop=shop_b,
            payslip=slip,
            staff=slip.staff,
            amount=slip.total,
            method=PaymentMethod.BANK,
            reference="JIRANI1",
            created_by=staff_b,
        )
    assert code_of(mpesa(staff_client_a, slip)) == (404, "not_found")
    assert code_of(cash(staff_client_a, slip)) == (404, "not_found")
    assert code_of(staff_client_a.post(void(made.pk), {"reason": "Kosa"}, format="json")) == (404, "not_found")


def test_an_id_another_shop_holds_is_taken(
    staff_client_a: APIClient, asha: Payslip, shop_b: Shop, staff_b: StaffMember
) -> None:
    # The app's id, held by a row of shop B: refused as taken, and nothing more about that row.
    with shop_context(shop_b):
        slip = Payslip.objects.create(
            shop=shop_b, staff=job(shop_b, "Jirani"), month=NOVEMBER, total=Decimal("5000.00"), created_by=staff_b
        )
        theirs = PayslipPayment.objects.create(
            shop=shop_b,
            payslip=slip,
            staff=slip.staff,
            amount=slip.total,
            method=PaymentMethod.BANK,
            reference="JIRANI1",
            created_by=staff_b,
        )
    answer = mpesa(staff_client_a, asha, id=str(theirs.pk))
    assert answer.status_code == 400
    assert answer.json()["fields"] == {"id": ["id.taken"]}


@pytest.mark.parametrize("missing", [Permission.PAY_RUN, Permission.SETTINGS_MANAGE, Permission.STAFF_MANAGE])
def test_each_key_of_handing_out_is_asked(
    shop_a: Shop, give_role: GiveRole, staff_a2: StaffMember, asha: Payslip, missing: Permission
) -> None:
    # A seller handed two of the three keys, on the whole shop, reaches none of the three routes; with the third, all.
    give_role(staff_a2, RoleTemplate.SELLER, None)
    with shop_context(shop_a):
        for key in (Permission.PAY_RUN, Permission.SETTINGS_MANAGE, Permission.STAFF_MANAGE):
            if key != missing:
                grant_permission(staff_a2, key, side=None, by=None)
        made = PayslipPayment.objects.create(
            shop=shop_a,
            payslip=asha,
            staff=asha.staff,
            amount=asha.total,
            method=PaymentMethod.BANK,
            reference="BENKI1",
            created_by=asha.created_by,
        )
    client = client_for(staff_a2)

    def asked() -> list[Any]:
        return [
            mpesa(client, asha),
            cash(client, asha),
            client.post(void(made.pk), {"reason": "Kosa"}, format="json"),
        ]

    for refused in asked():
        assert code_of(refused) == (403, "permission_denied")
        assert "152000" not in refused.content.decode()
    with shop_context(shop_a):
        grant_permission(staff_a2, missing, side=None, by=None)
    # Now the payment is crossed out, then Asha is paid by number, and the drawing finds her paid.
    answers = asked()
    assert [answer.status_code for answer in answers] == [400, 400, 200]
    assert [answers[0].json()["code"], answers[1].json()["code"]] == ["payment.already_paid", "payment.already_paid"]


def test_the_approval_key_alone_hands_out_nothing(
    shop_a: Shop, give_role: GiveRole, staff_a2: StaffMember, asha: Payslip
) -> None:
    # pay.approve and the two keys of pay, but no pay.run: approving is not handing out.
    give_role(staff_a2, RoleTemplate.SELLER, None)
    with shop_context(shop_a):
        for key in (Permission.PAY_APPROVE, Permission.SETTINGS_MANAGE, Permission.STAFF_MANAGE):
            grant_permission(staff_a2, key, side=None, by=None)
    assert code_of(mpesa(client_for(staff_a2), asha)) == (403, "permission_denied")


def test_a_signature_opens_only_with_the_keys_of_pay(
    shop_a: Shop, give_role: GiveRole, staff_client_a: APIClient, staff_a2: StaffMember, asha: Payslip
) -> None:
    # A manager holds pay.run but not the two keys of pay (02 §5): he sees nobody's pay, so no signature either.
    signature = uuid.uuid7()
    cash(staff_client_a, asha, signature=signature)
    give_role(staff_a2, RoleTemplate.MANAGER, None)
    client = client_for(staff_a2)
    assert code_of(client.get(signature_file(str(signature)))) == (403, "permission_denied")
    with shop_context(shop_a):
        grant_permission(staff_a2, Permission.SETTINGS_MANAGE, side=None, by=None)
    assert code_of(client.get(signature_file(str(signature)))) == (403, "permission_denied")
    with shop_context(shop_a):
        grant_permission(staff_a2, Permission.STAFF_MANAGE, side=None, by=None)
    assert client.get(signature_file(str(signature))).status_code == 200


def test_without_the_keys_of_pay_nothing_sent_is_read(
    give_role: GiveRole, staff_a2: StaffMember, asha: Payslip
) -> None:
    # A manager holds pay.run, every manager's, but not the two keys of pay (02 §5): refused before anything he sent is
    # read, so even a form that is wrong in every box answers only that he may not, never how it is wrong.
    give_role(staff_a2, RoleTemplate.MANAGER, None)
    with shop_context(asha.shop_id):
        made = PayslipPayment.objects.create(
            shop_id=asha.shop_id,
            payslip=asha,
            staff=asha.staff,
            amount=asha.total,
            method=PaymentMethod.BANK,
            reference="BENKI1",
            created_by=asha.created_by,
        )
    client = client_for(staff_a2)
    wrong = {"id": str(uuid.uuid4()), "method": "hundi", "reference": "Q" * 31}
    for answer in (
        client.post(by_number(asha.pk), wrong, format="json"),
        client.put(in_cash(asha.pk), data=b"", content_type="image/jpeg"),
        client.post(void(made.pk), {"reason": "u" * 201}, format="json"),
    ):
        assert code_of(answer) == (403, "permission_denied")
