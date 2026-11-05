"""apps/core/tests/test_acting.py — tests for telling PostgreSQL who acts in a visit (apps/core/acting.py,
ADR-0036).

The trigger that records office edits names who made each one and from which device, and refuses an edit of another
shop's row (CTRL-2, AUTH-8). It reads them from three settings of the database session, `mpc.staff_id`, `mpc.shop_id`
and `mpc.device_id`, which every office visit fills while it runs and empties as it ends:

    before the visit     during the visit (staff A of shop A, laptop L)     after the visit
    "", "", ""           A's id, shop A's id, L's id                        "", "", ""

The last test serves its own small office route, built on the base view as every office route is, from this module's
address list (`urlpatterns`, below; pytest-django's `urls` mark), so the shared probe routes stay as they are. `core`
may not import `people` (ADR-0035), so the staff member and the device come from backend/conftest.py, typed as an Actor
and a ShopScoped row.
"""

import uuid
from dataclasses import dataclass

import pytest
from django.db import DataError, connection, transaction
from django.urls import path
from pytest_django import DjangoAssertNumQueries
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.test import APIClient

from apps.core.acting import DEVICE_SETTING, SHOP_SETTING, STAFF_SETTING, acting_as, current_device_id
from apps.core.api.base import SEES_THE_SIDE, ShopViewSet
from apps.core.models import ShopScoped
from apps.core.tenancy import Actor, ShopMismatch
from tests.probe.models import Note

pytestmark = pytest.mark.django_db


@dataclass(frozen=True)
class Someone:
    # An Actor made up for the test (apps/core/tenancy.py): who acts needs only these two.
    shop_id: uuid.UUID
    staff_id: uuid.UUID | None


def told() -> tuple[str, str]:
    # What PostgreSQL holds right now, as the trigger reads it: who acts, and the visit's shop. "" for nobody, no
    # shop; a session that never set them answers NULL, read as "" too.
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_setting(%s, true), current_setting(%s, true)", [STAFF_SETTING, SHOP_SETTING])
        row = cursor.fetchone()
    assert row is not None
    return row[0] or "", row[1] or ""


def told_device() -> str:
    # The device PostgreSQL holds right now, as the trigger reads it: "" for none.
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_setting(%s, true)", [DEVICE_SETTING])
        row = cursor.fetchone()
    assert row is not None
    return row[0] or ""


def test_acting_as_tells_the_device_and_puts_it_back(staff_a: Actor, device_a: ShopScoped) -> None:
    # X3: a visit that knows its device tells PostgreSQL, for the trigger, and the audit book reads the same note.
    shop = staff_a.shop_id
    assert (told_device(), current_device_id(shop)) == ("", None)
    with acting_as(staff_a, device=device_a):
        assert (told_device(), current_device_id(shop)) == (str(device_a.pk), device_a.pk)
    assert (told_device(), current_device_id(shop)) == ("", None)
    # Put back however the block ends: a failed visit must not leave its device on the connection for the next one,
    # or that visit's edits would name a laptop nobody used.
    with pytest.raises(RuntimeError), acting_as(staff_a, device=device_a):
        raise RuntimeError("The visit failed.")
    assert told_device() == ""


def test_current_device_is_refused_for_another_shops_row(staff_a: Actor, device_a: ShopScoped) -> None:
    # T1: the trigger refuses to record a row of another shop than the visit's, and the audit book's read does too.
    with acting_as(staff_a, device=device_a), pytest.raises(ShopMismatch):
        current_device_id(uuid.uuid7())
    # With no device there is nothing to name, so nothing to refuse: the system may work across shops (03 §5.11).
    with acting_as(staff_a, device=None):
        assert current_device_id(uuid.uuid7()) is None
    assert current_device_id(uuid.uuid7()) is None


def test_inner_block_keeps_the_visits_device(staff_a: Actor, staff_a2: Actor, device_a: ShopScoped) -> None:
    # editing() and the staff services open a block of their own for `by`, mid-visit. Had it wiped the device, every
    # edit made through them would name nobody's device, and the edit history would stay silent on its most common path.
    with acting_as(staff_a, device=device_a):
        with acting_as(staff_a2):
            assert told() == (str(staff_a2.staff_id), str(staff_a2.shop_id))
            assert told_device() == str(device_a.pk)
        assert told_device() == str(device_a.pk)


def test_block_outside_a_visit_has_no_device_to_keep(staff_a: Actor) -> None:
    # A nightly job that passes its own `by`: the person is named, and no device, since the system used none.
    with acting_as(staff_a):
        assert told_device() == ""


def test_visit_says_it_has_no_device(staff_a: Actor, device_a: ShopScoped) -> None:
    # None is not "leave it": a visit with no device, on a connection another block left a device on, names none.
    with acting_as(staff_a, device=device_a):
        with acting_as(staff_a, device=None):
            assert told_device() == ""
        assert told_device() == str(device_a.pk)


def test_device_stays_inside_its_own_shop(staff_a: Actor, device_a: ShopScoped) -> None:
    # T1: a device belongs to one shop. A block for another shop's actor doesn't carry it along, or that shop's history
    # would name this shop's laptop; back in its own shop's block, the device is there again.
    with acting_as(staff_a, device=device_a):
        with acting_as(Someone(uuid.uuid7(), uuid.uuid7())):
            assert told_device() == ""
        assert told_device() == str(device_a.pk)


def test_acting_as_refuses_another_shops_device(
    device_a: ShopScoped, django_assert_num_queries: DjangoAssertNumQueries
) -> None:
    # T1: a bug in the calling code, stopped before PostgreSQL is told anything: no query is sent, and the block never
    # runs, so nothing can be written that names this device in another shop's history.
    with (
        django_assert_num_queries(0),
        pytest.raises(ShopMismatch),
        acting_as(Someone(uuid.uuid7(), uuid.uuid7()), device=device_a),
    ):
        pytest.fail("The block must not run.")


def test_acting_as_puts_back_who_acted_before() -> None:
    shop = uuid.uuid7()
    other_shop = uuid.uuid7()
    owner = Someone(shop, uuid.uuid7())
    manager = Someone(other_shop, uuid.uuid7())
    assert told() == ("", "")

    with acting_as(owner):
        assert told() == (str(owner.staff_id), str(shop))
        # Inside another block, the inner one acts; after it, the outer one again, as with shop_context().
        with acting_as(manager):
            assert told() == (str(manager.staff_id), str(other_shop))
        assert told() == (str(owner.staff_id), str(shop))
        # A device alone is no person (03 §5.4): nobody is named, and its shop is still checked.
        with acting_as(Someone(shop, None)):
            assert told() == ("", str(shop))
        # Put back however the block ends, an error included: a failed visit must not leave its person or its shop
        # on the connection for the next one.
        with pytest.raises(RuntimeError), acting_as(manager):
            raise RuntimeError("The visit failed.")
        assert told() == (str(owner.staff_id), str(shop))

    assert told() == ("", "")


def test_acting_as_costs_two_queries(device_a: ShopScoped, django_assert_num_queries: DjangoAssertNumQueries) -> None:
    # Every office visit opens it, reads included, so it stays cheap: one query to read the old values and write the
    # new ones together, one to put the old ones back. The device, named or not, adds none.
    with django_assert_num_queries(2), acting_as(Someone(uuid.uuid7(), uuid.uuid7())):
        pass
    with django_assert_num_queries(2), acting_as(Someone(device_a.shop_id, uuid.uuid7()), device=device_a):
        pass


def test_acting_as_leaves_a_failed_transaction_to_its_rollback() -> None:
    # A query that fails inside a transaction leaves it broken: PostgreSQL refuses every query after it until the
    # rollback. Putting the old values back with a query then would fail too, and its error would hide the real one.
    # The rollback puts them back anyway, since they were changed inside the same transaction.
    owner = Someone(uuid.uuid7(), uuid.uuid7())
    with (
        pytest.raises(DataError, match="division by zero"),
        transaction.atomic(),
        acting_as(owner),
        connection.cursor() as cursor,
    ):
        cursor.execute("SELECT 1 / 0")
    assert told() == ("", "")


def test_acting_as_leaves_a_broken_atomic_block_to_its_rollback() -> None:
    # The other way a transaction breaks: a step inside an atomic block with no savepoint of its own fails in Python,
    # with no failed query. PostgreSQL sees nothing wrong, but Django marks the whole transaction for rollback
    # (needs_rollback) and refuses every query until then: putting the old values back would hide the real error too.
    owner = Someone(uuid.uuid7(), uuid.uuid7())
    with (
        pytest.raises(RuntimeError, match="A step failed"),
        transaction.atomic(),
        acting_as(owner),
        transaction.atomic(savepoint=False),
    ):
        raise RuntimeError("A step failed.")
    assert told() == ("", "")


def test_outer_device_survives_a_failed_inner_block(staff_a: Actor, device_a: ShopScoped) -> None:
    # A step that fails mid-visit, inside its own savepoint, is undone with what it told PostgreSQL. The visit goes on,
    # so its device must still be there for its next edit: both ways a transaction breaks, as in the two tests above.
    with acting_as(staff_a, device=device_a):
        with (
            pytest.raises(DataError, match="division by zero"),
            transaction.atomic(),
            acting_as(staff_a, device=None),
            connection.cursor() as cursor,
        ):
            assert told_device() == ""
            cursor.execute("SELECT 1 / 0")
        assert told_device() == str(device_a.pk)

        with (
            pytest.raises(RuntimeError, match="A step failed"),
            transaction.atomic(),
            acting_as(staff_a, device=None),
            transaction.atomic(savepoint=False),
        ):
            assert told_device() == ""
            raise RuntimeError("A step failed.")
        assert told_device() == str(device_a.pk)
    assert told_device() == ""


class WhoActsViewSet(ShopViewSet[Note]):
    # An office route like any other, whose one answer is what PostgreSQL holds as who acts and the visit's shop,
    # while the visit runs.
    model = Note
    side_field = None
    # It shows what PostgreSQL holds and changes nothing: seeing the shop is enough (PPL-5).
    action_permissions = {"list": SEES_THE_SIDE}

    def list(self, request: Request) -> Response:
        staff, shop = told()
        return Response({"staff": staff, "shop": shop})


urlpatterns = [path("who-acts/", WhoActsViewSet.as_view({"get": "list"}))]


@pytest.mark.urls(__name__)
def test_office_visit_tells_the_database_who_acts(staff_client_a: APIClient, staff_a: Actor) -> None:
    answer = staff_client_a.get("/who-acts/")

    assert answer.status_code == 200
    assert answer.json() == {"staff": str(staff_a.staff_id), "shop": str(staff_a.shop_id)}
    # Taken back as the visit ended: the next query on this connection, outside any visit, names nobody, no shop.
    assert told() == ("", "")
