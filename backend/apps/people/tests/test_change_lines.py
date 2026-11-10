"""apps/people/tests/test_change_lines.py — each staff service writes the person's line in the shop's change log
(SYNC-15).

A shared laptop keeps a copy of the shop's people at work (apps/sync/registry.py): their names, status, when their PIN
last changed, and their keys, all on their staff row. It learns what changed only from the shop's change log (SYNC-3's
pull), so every service that changes one of those names the person's job: `upsert` while they still work there,
`archive` when they leave, as a laptop then drops them. A role or an extra key is its own row on the server, but it
travels on the person's staff row, so it names the person. A refused change names nothing. The lines are read from
where each save starts (backend/tests/change_log.py).
"""

import pytest
from django.core.exceptions import ValidationError

from apps.core.models import ChangeOp
from apps.core.permissions import Permission, RoleTemplate
from apps.core.tenancy import shop_context
from apps.people.models import User
from apps.people.selectors import shop_today
from apps.people.services import (
    add_staff,
    assign_role,
    copy_role_templates,
    grant_permission,
    mark_left,
    set_pin,
    suspend,
    unsuspend,
)
from apps.shops.models import Shop, Side
from tests.change_log import lines_written

pytestmark = pytest.mark.django_db

UPSERT = ChangeOp.UPSERT
ARCHIVE = ChangeOp.ARCHIVE


def test_each_service_records_its_change(shop_a: Shop, side_a: Side) -> None:
    # Juma's working life at the shop, one save at a time: each lands one line naming his job, and nothing else.
    user = User.objects.create_user(full_name="Juma Mfano")
    with shop_context(shop_a):
        roles = copy_role_templates(shop_a)  # roles stay on the server: no line of their own
        with lines_written(shop_a) as added:
            juma = add_staff(shop=shop_a, user=user, display_name="Juma", by=None)
        with lines_written(shop_a) as given_a_pin:
            set_pin(juma, "2580", by=None)
        with lines_written(shop_a) as given_a_role:
            assign_role(juma, roles[RoleTemplate.SELLER], side=side_a, by=None)
        with lines_written(shop_a) as given_a_key:
            grant_permission(juma, Permission.STOCK_COUNT, side=side_a, by=None)
        with lines_written(shop_a) as suspended:
            suspend(juma, by=None, reason="Hakuja kazini")
        with lines_written(shop_a) as back:
            unsuspend(juma, by=None, reason="Amerudi")
        with lines_written(shop_a) as left:
            mark_left(juma, left_on=shop_today(shop_a), by=None, reason="Amehamia mji mwingine")
        # Someone who has left can't be suspended: refused, so no line.
        with lines_written(shop_a) as refused, pytest.raises(ValidationError):
            suspend(juma, by=None, reason="Hakuja kazini")

    job = ("staff", juma.pk)
    for lines in (added, given_a_pin, given_a_role, given_a_key, suspended, back):
        assert lines == [(*job, UPSERT)]
    # He left: every laptop drops him, as the PIN screen no longer shows him.
    assert left == [(*job, ARCHIVE)]
    assert refused == []
