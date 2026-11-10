"""apps/sync/tests/test_pushed_document.py — the answer log: the answer the push gave each document, kept so that the
same document sent again gets the same answer (SYNC-4; 03 §5.5, §6.3).

    shop  document  laptop          #   answer    change no.  flags   reason
    MPC   0193…a7   Laptop ya Dawa  12  accepted  43          —       —
    MPC   0193…b2   Laptop ya Dawa  13  invalid   —           1 flag  document.type_unknown

These tests pin the rules the database keeps on it (PushedDocument, apps/sync/models.py): a line is never changed or
deleted; one line per document in a shop, while another shop may keep its own; an answer that makes sense for its
status; the flag an invalid document raises, about its line; and the shop guard. What the push writes in it, and when,
is test_push.py's. Fake data only: the repo is public.
"""

import datetime as dt
import uuid

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.models import Model

from apps.control.models import FlagKind
from apps.control.services import raise_flag
from apps.core.models import AppendOnlyError, ShopScoped
from apps.core.tenancy import NoShopSelected, shop_context
from apps.people.models import Device, StaffMember
from apps.shops.models import Shop, Side
from apps.sync.models import PushedDocument, PushedStatus

pytestmark = pytest.mark.django_db

# Asha's sale: made at 10:42 by the laptop's clock, received at 14:05 by the server's, both in UTC (03 §6.6).
SALE_ID = uuid.UUID("0193a000-0000-7000-8000-0000000000a7")
CLIENT_TIME = dt.datetime(2026, 11, 10, 7, 42, tzinfo=dt.UTC)
RECEIVED_AT = dt.datetime(2026, 11, 10, 11, 5, tzinfo=dt.UTC)


def _line(shop: Model, device: ShopScoped, **changes: object) -> PushedDocument:
    # The answer log's line for Asha's sale, accepted at change 43; `changes` overrides a fact.
    facts: dict[str, object] = {
        "shop_id": shop.pk,
        "device_id": device.pk,
        "device_seq": 12,
        "client_time": CLIENT_TIME,
        "received_at": RECEIVED_AT,
        "document_id": SALE_ID,
        "type": "sale",
        "schema_version": 1,
        "status": PushedStatus.ACCEPTED,
        "posted_seq": 43,
    }
    facts.update(changes)
    return PushedDocument(**facts)


@pytest.fixture
def line(shop_a: Model, device_a: ShopScoped) -> PushedDocument:
    row = _line(shop_a, device_a)
    row.save()
    return row


@pytest.fixture
def device_b(shop_b: Shop, side_b: Side) -> Device:
    # A laptop of the second shop, for the tests where shop B's push meets an id shop A already holds. Only the row,
    # as device_a is (backend/conftest.py).
    with shop_context(shop_b):
        return Device.objects.create(shop=shop_b, home_side=side_b, name="Laptop B", code=1, key_hash="b" * 64)


def test_a_stored_answer_is_never_changed(shop_a: Model, line: PushedDocument) -> None:
    # The answer is the one the laptop got the first time, and every repeat gets that same answer (03 §5.5). A line
    # that could change would answer a repeat differently: never in Python, never in PostgreSQL, whatever sends it.
    line.posted_seq = 44
    with pytest.raises(AppendOnlyError):
        line.save()
    with (
        pytest.raises(IntegrityError, match="append-only"),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute(f"UPDATE {PushedDocument._meta.db_table} SET posted_seq = 44 WHERE id = %s", [line.pk])
    with shop_context(shop_a), pytest.raises(IntegrityError, match="append-only"), transaction.atomic():
        PushedDocument.objects.filter(pk=line.pk).delete()
    line.refresh_from_db()
    assert line.posted_seq == 43


def test_one_answer_per_document_in_a_shop(shop_a: Model, device_a: ShopScoped, line: PushedDocument) -> None:
    # Two copies of one sale, sent at the same moment by a laptop that thought the first was lost: only one line can
    # be written, so the second copy is refused here and finds the first one's answer (SYNC-4's push).
    with pytest.raises(IntegrityError, match="sync_pusheddocument_one_per_document"):
        _line(shop_a, device_a, device_seq=13).save()


def test_another_shop_keeps_its_own_answer_for_the_same_id(
    shop_b: Model, device_b: Device, line: PushedDocument
) -> None:
    # Shop B's laptop sends a document with an id shop A already holds (03 §5.4). B's answer, `id.taken`, is kept in
    # B's own line, so B's repeat gets it again, and it says nothing about A's sale: neither shop's line is in the
    # other's way.
    other = _line(shop_b, device_b, status=PushedStatus.INVALID, posted_seq=None, reason="id.taken")
    other.save()
    with shop_context(shop_b):
        assert PushedDocument.objects.get(document_id=SALE_ID).reason == "id.taken"


@pytest.mark.parametrize(
    ("changes", "rule"),
    [
        # An invalid document with no reason: whoever reads its flag can't tell what to fix.
        ({"status": PushedStatus.INVALID, "posted_seq": None}, "invalid_has_only_a_reason"),
        # An invalid document saved nothing, so it took no change number: a laptop would wait for one forever.
        ({"status": PushedStatus.INVALID, "reason": "document.type_unknown"}, "invalid_has_only_a_reason"),
        # An accepted document has nothing to be refused for: no reason, and no wrong fields either.
        ({"reason": "document.type_unknown"}, "accepted_has_no_reason"),
        ({"reason_fields": {"text": ["max_length"]}}, "accepted_has_no_reason"),
        # An invalid document saved nothing, so it raised no flag of its own rules: its one flag is about its line.
        (
            {
                "status": PushedStatus.INVALID,
                "posted_seq": None,
                "reason": "invalid",
                "flags": [{"id": "0193a000-0000-7000-8000-0000000000f1", "kind": "negative_stock"}],
            },
            "invalid_has_only_a_reason",
        ),
        # "duplicate" is never stored: it is the first answer, given again.
        ({"status": "duplicate"}, "status_known"),
        # A laptop numbers its documents from 1, as the change log does.
        ({"device_seq": 0}, "device_seq_from_one"),
    ],
    ids=[
        "invalid_with_no_reason",
        "invalid_with_a_change_number",
        "accepted_with_a_reason",
        "accepted_with_wrong_fields",
        "invalid_with_flags",
        "duplicate",
        "seq_0",
    ],
)
def test_an_answer_must_make_sense(shop_a: Model, device_a: ShopScoped, changes: dict[str, object], rule: str) -> None:
    with pytest.raises(IntegrityError, match=f"sync_pusheddocument_{rule}"):
        _line(shop_a, device_a, **changes).save()


def test_an_invalid_document_raises_its_own_flag(shop_a: Model, device_a: ShopScoped, staff_a: StaffMember) -> None:
    # The laptop sets an invalid document aside under "needs attention", and the server raises a flag (03 §6.3), about
    # the document's line, so a manager sees which document failed and why, and who made it.
    invalid = _line(shop_a, device_a, status=PushedStatus.INVALID, posted_seq=None, reason="document.type_unknown")
    invalid.save()
    with shop_context(shop_a):
        flag = raise_flag(kind=FlagKind.INVALID_DOCUMENT, subject=invalid, people=[staff_a], by=None)
        assert (flag.subject_type, flag.subject) == ("pushed_document", invalid)


def test_pushed_documents_keep_the_shop_guard(shop_b: Model, shop_a: Model, line: PushedDocument) -> None:
    # Built on two bases, AppendOnly and CounterRecord: the guard stays the default, as on every shop's table
    # (ADR-0022). A shop's answer log is its own: shop B's push never finds shop A's answers.
    with pytest.raises(NoShopSelected):
        PushedDocument.objects.count()
    with shop_context(shop_b):
        assert not PushedDocument.objects.exists()
    with shop_context(shop_a):
        assert PushedDocument.objects.get() == line
