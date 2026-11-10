"""apps/core/tests/test_counter_record.py — tests for CounterRecord, the base of every record made at a shop's counter
(02 §1, 03 §5.3; SYNC-4).

A record made at the counter, a sale or a clock-in, is made on a device, often offline, and reaches the server later,
in a push. It keeps four facts the server can't work out for itself:

    device          device_seq   client_time   received_at
    Laptop ya Dawa  12           10:42         14:05
    which laptop    its number   its clock     the server's clock when the push arrived

These tests pin what the base gives: the four facts kept as saved, none of them left out, a device that made records
never deleted, and the shop guard every shop's table has. The table is `probe.Ticket`, a test-only table built on
CounterRecord (backend/tests/probe/), standing for a sale: core may not name a higher app's table (ADR-0041). The
device comes from backend/conftest.py, typed by its base, as core's tests may not name `people`'s tables either.
"""

import datetime as dt

import pytest
from django.db import IntegrityError
from django.db.models import Model, ProtectedError

from apps.core.models import ShopScoped
from apps.core.tenancy import NoShopSelected, shop_context
from tests.probe.models import Ticket

pytestmark = pytest.mark.django_db

# Asha served the customer at 10:42 by the laptop's clock, three minutes slow; the push reached the server at 14:05,
# once the network came back. Both in UTC, as every time is stored (03 §6.6): 10:42 and 14:05 in Arusha are 07:42 and
# 11:05 there.
CLIENT_TIME = dt.datetime(2026, 11, 10, 7, 42, tzinfo=dt.UTC)
RECEIVED_AT = dt.datetime(2026, 11, 10, 11, 5, tzinfo=dt.UTC)


def _ticket(shop: Model, device: ShopScoped, **changes: object) -> Ticket:
    # A ticket of the shop, made on the device, as its twelfth record; `changes` overrides or leaves out a fact.
    facts: dict[str, object] = {
        "shop_id": shop.pk,
        "device_id": device.pk,
        "device_seq": 12,
        "client_time": CLIENT_TIME,
        "received_at": RECEIVED_AT,
        "text": "2 bags of pumba",
    }
    facts.update(changes)
    return Ticket(**facts)


def test_counter_record_keeps_the_device_its_number_and_both_clocks(shop_a: Model, device_a: ShopScoped) -> None:
    # What the laptop said and what the server saw, read back exactly as saved: the device that made it, its number on
    # that device, the time the device's clock showed, and the server's time when it arrived.
    _ticket(shop_a, device_a).save()
    with shop_context(shop_a):
        ticket = Ticket.objects.get()
    assert (ticket.device_id, ticket.device_seq) == (device_a.pk, 12)
    assert (ticket.client_time, ticket.received_at) == (CLIENT_TIME, RECEIVED_AT)


@pytest.mark.parametrize("fact", ["device_id", "device_seq", "client_time", "received_at"])
def test_counter_record_needs_all_four_facts(shop_a: Model, device_a: ShopScoped, fact: str) -> None:
    # A record with no device can't be traced to the laptop that made it, nor flagged there; one with no number can't
    # be put in order, nor its gaps found (SYNC-5); and with no clock, there is no time at all. So each is required by
    # the database itself, whichever code writes the row.
    with pytest.raises(IntegrityError, match="not-null"):
        _ticket(shop_a, device_a, **{fact: None}).save()


def test_a_device_with_counter_records_is_never_deleted(shop_a: Model, device_a: ShopScoped) -> None:
    # Nothing is deleted (rule 7): a laptop that made sales keeps its row, so every sale still names the laptop it came
    # from. A laptop taken out of use is blocked, not deleted (AUTH-1).
    ticket = _ticket(shop_a, device_a)
    ticket.save()
    with shop_context(shop_a), pytest.raises(ProtectedError) as refusal:
        device_a.delete()
    assert ticket in refusal.value.protected_objects


def test_counter_record_keeps_the_shop_guard(shop_a: Model, shop_b: Model, device_a: ShopScoped) -> None:
    # A base with a Meta of its own can lose the guard if it is written wrong (CORE-1): a read must still name its shop,
    # and see that shop's rows only (ADR-0042).
    _ticket(shop_a, device_a).save()
    with pytest.raises(NoShopSelected):
        Ticket.objects.count()
    with shop_context(shop_b):
        assert not Ticket.objects.exists()
    with shop_context(shop_a):
        assert Ticket.objects.count() == 1
