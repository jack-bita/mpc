"""apps/core/tests/test_acting.py — tests for telling PostgreSQL who acts in a visit (apps/core/acting.py,
ADR-0036).

The trigger that records office edits names who made each one (CTRL-2). It reads that from a setting of the
database session, `mpc.staff_id`, which every office visit fills while it runs and empties as it ends:

    before the visit     during the visit (staff A)     after the visit
    "" (nobody)          A's id                         "" (nobody)

The second test serves its own small office route, built on the base view as every office route is, from this
module's address list (`urlpatterns`, below; pytest-django's `urls` mark), so the shared probe routes stay as
they are. `core` may not import `people` (ADR-0035), so the staff member comes from backend/conftest.py, typed
as an Actor.
"""

import uuid
from dataclasses import dataclass

import pytest
from django.db import connection
from django.urls import path
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.test import APIClient

from apps.core.acting import STAFF_SETTING, acting_as
from apps.core.api.base import ShopViewSet
from apps.core.tenancy import Actor
from tests.probe.models import Note

pytestmark = pytest.mark.django_db


@dataclass(frozen=True)
class Someone:
    # An Actor made up for the test (apps/core/tenancy.py): who acts needs only these two.
    shop_id: uuid.UUID
    staff_id: uuid.UUID | None


def who_acts() -> str | None:
    # What PostgreSQL holds right now, as the trigger reads it: None if this session never set it, "" for nobody.
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_setting(%s, true)", [STAFF_SETTING])
        row = cursor.fetchone()
    assert row is not None
    value: str | None = row[0]
    return value


def test_acting_as_puts_back_who_acted_before() -> None:
    shop = uuid.uuid7()
    owner = Someone(shop, uuid.uuid7())
    manager = Someone(shop, uuid.uuid7())
    assert (who_acts() or "") == ""

    with acting_as(owner):
        assert who_acts() == str(owner.staff_id)
        # Inside another block, the inner one acts; after it, the outer one again, as with shop_context().
        with acting_as(manager):
            assert who_acts() == str(manager.staff_id)
        assert who_acts() == str(owner.staff_id)
        # A device alone is no person (03 §5.4): nobody is named.
        with acting_as(Someone(shop, None)):
            assert who_acts() == ""
        # Put back however the block ends, an error included: a failed visit must not leave its person on the
        # connection for the next one.
        with pytest.raises(RuntimeError), acting_as(manager):
            raise RuntimeError("The visit failed.")
        assert who_acts() == str(owner.staff_id)

    assert who_acts() == ""


class WhoActsViewSet(ShopViewSet[Note]):
    # An office route like any other, whose one answer is what PostgreSQL holds as who acts, while the visit runs.
    model = Note
    side_field = None

    def list(self, request: Request) -> Response:
        return Response({"who_acts": who_acts()})


urlpatterns = [path("who-acts/", WhoActsViewSet.as_view({"get": "list"}))]


@pytest.mark.urls(__name__)
def test_office_visit_tells_the_database_who_acts(staff_client_a: APIClient, staff_a: Actor) -> None:
    answer = staff_client_a.get("/who-acts/")

    assert answer.status_code == 200
    assert answer.json() == {"who_acts": str(staff_a.staff_id)}
    # Taken back as the visit ended: the next query on this connection, outside any visit, names nobody.
    assert who_acts() == ""
