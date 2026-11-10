"""apps/people/tests/test_change_lines.py — each staff service writes the person's line in the shop's change log
(SYNC-15).

A shared laptop keeps a copy of the shop's people at work (apps/sync/registry.py): their names, status, when their PIN
last changed, and their keys, all on their staff row. It learns what changed only from the shop's change log (SYNC-3's
pull), so every service that changes one of those names the person's job: `upsert` while they still work there,
`archive` when they leave, as a laptop then drops them. A role or an extra key is its own row on the server, but it
travels on the person's staff row, so it names the person. A refused change names nothing. The lines are read from
where each save starts (backend/tests/change_log.py). The superuser's changes to a person in the admin, their name,
language or switch-off, reach every shop where they work, as the person belongs to no shop (change_person).
"""

import pytest
from django.core.exceptions import ValidationError
from django.db.transaction import TransactionManagementError

from apps.core.models import ChangeOp
from apps.core.permissions import Permission, RoleTemplate
from apps.core.tenancy import shop_context
from apps.people.models import StaffMember, User
from apps.people.selectors import shop_today
from apps.people.services import (
    _record_each_job,
    add_staff,
    assign_role,
    change_person,
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


def test_a_person_switched_off_leaves_every_shops_laptops(staff_a: StaffMember, shop_b: Shop) -> None:
    # The superuser switches Juma off in the admin (User.is_active): he can log in nowhere, so each shop's laptops drop
    # him, as the bootstrap no longer sends him (staff_rows). An archive line in every shop where he works; switched on
    # again, an upsert line in each, as he is sent once more.
    juma = User.objects.get(pk=staff_a.user_id)
    with shop_context(shop_b):
        at_b = add_staff(shop=shop_b, user=juma, display_name="Juma", by=None)
    with lines_written(staff_a.shop_id) as off_a, lines_written(shop_b) as off_b:
        juma.is_active = False
        change_person(juma, changed=["is_active"])
    with lines_written(staff_a.shop_id) as on_a, lines_written(shop_b) as on_b:
        juma.is_active = True
        change_person(juma, changed=["is_active"])

    assert (off_a, off_b) == ([("staff", staff_a.pk, ARCHIVE)], [("staff", at_b.pk, ARCHIVE)])
    assert (on_a, on_b) == ([("staff", staff_a.pk, UPSERT)], [("staff", at_b.pk, UPSERT)])


def test_a_persons_name_or_language_reaches_every_shop(staff_a: StaffMember) -> None:
    # The name on Juma's tile, and the language his screens speak, travel on his staff row too.
    juma = User.objects.get(pk=staff_a.user_id)
    for field, value in (("full_name", "Juma Mfano Mpya"), ("language", "en")):
        with lines_written(staff_a.shop_id) as lines:
            setattr(juma, field, value)
            change_person(juma, changed=[field])
        assert lines == [("staff", staff_a.pk, UPSERT)], field
    assert User.objects.get(pk=juma.pk).full_name == "Juma Mfano Mpya"


def test_a_change_no_laptop_shows_writes_no_line(staff_a: StaffMember) -> None:
    # A phone never leaves the server (SYNC-2's secrets check): changing it alone tells no laptop anything.
    juma = User.objects.get(pk=staff_a.user_id)
    with lines_written(staff_a.shop_id) as lines:
        juma.phone = "+255700000001"
        change_person(juma, changed=["phone"])

    assert lines == []
    assert User.objects.get(pk=juma.pk).phone == "+255700000001"


@pytest.mark.django_db(transaction=True)
def test_a_persons_lines_need_the_transaction_that_saved_them(staff_a: StaffMember) -> None:
    # Outside a transaction, each shop's line would commit on its own, and a failure after it would leave a laptop told
    # of a change to the person that never happened. So writing them outside one is refused, before any line. A normal
    # test always runs inside its own transaction, which hides this: `transaction=True` runs it with none open.
    juma = User.objects.get(pk=staff_a.user_id)
    refused = pytest.raises(TransactionManagementError, match="inside the transaction that saved the person")
    with lines_written(staff_a.shop_id) as lines, refused:
        _record_each_job(juma)

    assert lines == []
