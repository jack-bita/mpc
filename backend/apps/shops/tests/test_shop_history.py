"""apps/shops/tests/test_shop_history.py — the shops' office tables keep the history of their edits (03 §5.16,
ADR-0036): sides, payment accounts and stock locations.

The owner renames the side Dawa through the office route, as the settings screen will (SHOP-3). PostgreSQL's own
trigger writes one control.EditEvent: who (the staff member the visit names), when, and the name before and after:

    who       row                  before              after
    Staff A   side Dawa            name: Dawa          name: Dawa za Mifugo
    Staff A   M-Pesa Dawa account  number: 0755000111  number: 0755999888

The version and who edited last, which every edit moves (CORE-6), are left out: the history row keeps who and
when itself. The staff member is typed Any: `shops` may not name `people`'s StaffMember, not even in its tests
(ADR-0035).
"""

from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.control.models import EditEvent
from apps.core.acting import acting_as
from apps.core.tenancy import shop_context
from apps.shops.models import PaymentAccount, PaymentAccountKind, Shop, Side
from apps.shops.services import rename_side

pytestmark = pytest.mark.django_db


def test_office_edit_recorded_with_person(staff_client_a: APIClient, staff_a: Any, shop_a: Shop, side_a: Side) -> None:
    response = staff_client_a.patch(f"/api/v1/shops/sides/{side_a.pk}/", {"name": "Dawa za Mifugo", "version": 1})

    assert response.status_code == 200
    with shop_context(shop_a):
        [edit] = EditEvent.objects.filter(subject_type="side", subject_id=side_a.pk)
        # The visit's staff member, told to PostgreSQL by the base view (apps/core/acting.py).
        assert edit.created_by_id == staff_a.pk
        assert (edit.before, edit.after) == ({"name": "Dawa"}, {"name": "Dawa za Mifugo"})
        assert edit.subject == side_a


def test_payment_account_number_change_recorded(shop_a: Shop, staff_a: Any) -> None:
    # Jack's story at CTRL-2's review: someone changes the Dawa M-Pesa till's number to their own phone, and customers
    # pay the wrong number for a week. The history says who changed it, and when. No account screen exists yet
    # (SHOP-3), so the change is a plain update() inside a visit, opened here as the base view opens it. Fake numbers
    # only: the repo is public (03 §10).
    with shop_context(shop_a):
        account = PaymentAccount.objects.create(
            shop=shop_a,
            kind=PaymentAccountKind.MOBILE_MONEY,
            name="M-Pesa Dawa",
            provider="M-Pesa",
            number="0755000111",
        )
    with shop_context(shop_a), acting_as(staff_a):
        PaymentAccount.objects.filter(pk=account.pk).update(number="0755999888")
        [edit] = EditEvent.objects.filter(subject_type="payment_account", subject_id=account.pk)

    assert edit.created_by_id == staff_a.pk
    assert (edit.before, edit.after) == ({"number": "0755000111"}, {"number": "0755999888"})


def test_service_edit_names_its_by_outside_a_visit(staff_a: Any, shop_a: Shop, side_a: Side) -> None:
    # A service takes who acts as `by` and records it as the side's `updated_by` (editing(), CORE-6). The history
    # must name the same person, even where no visit told PostgreSQL anyone, as in a job or a command: two places
    # for one fact must never disagree (02 v1.7).
    with shop_context(shop_a):
        renamed = rename_side(side_a, version=1, name="Dawa za Mifugo", by=staff_a)
        [edit] = EditEvent.objects.filter(subject_type="side", subject_id=side_a.pk)

    assert renamed.updated_by_id == staff_a.pk
    assert edit.created_by_id == staff_a.pk
