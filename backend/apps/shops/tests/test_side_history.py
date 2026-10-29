"""apps/shops/tests/test_side_history.py — a side keeps the history of its edits (03 §5.16, ADR-0036).

The owner renames the side Dawa through the office route, as the settings screen will (SHOP-3). PostgreSQL's own
trigger writes one control.EditEvent: who (the staff member the visit names), when, and the name before and after:

    who       row          before          after
    Staff A   side Dawa    name: Dawa      name: Dawa za Mifugo

The version and who edited last, which every edit moves (CORE-6), are left out: the history row keeps who and
when itself. The staff member is typed Any: `shops` may not name `people`'s StaffMember, not even in its tests
(ADR-0035).
"""

from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.control.models import EditEvent
from apps.core.tenancy import shop_context
from apps.shops.models import Shop, Side

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
