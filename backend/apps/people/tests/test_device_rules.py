"""apps/people/tests/test_device_rules.py — the database's own rules on devices and pairing requests (AUTH-1; 03 §5.6).

The services check most of these first and answer with a code (apps/people/services.py), but the database is the
last guard: code that writes a row some other way, a bulk insert, a later service, SQL typed by hand, still can't
store a device without a hash, two devices with one code, or a request confirmed by half. One run per rule, and each
run names the rule it expects, as the side's rules do (apps/shops/tests/test_sides.py): a refusal by another rule
would hide a broken one. So a later migration that drops or mistypes a rule turns CI red. Fake data only: the repo is
public (03 §10).
"""

from datetime import timedelta
from typing import Any

import pytest
from django.db import IntegrityError
from django.utils import timezone

from apps.core.tenancy import shop_context
from apps.people.models import Device, PairingRequest
from apps.shops.models import Shop, Side

pytestmark = pytest.mark.django_db

# What a hash looks like: 64 hexadecimal characters. And what a key looks like, which must never be stored instead.
HASH = "a" * 64
OTHER_HASH = "b" * 64
A_KEY = "T2ceJdSY_9QrCo71uH-9CwsMf20d8I1J8t97cE4Lx0w"


def device_row(shop: Shop, side: Side, **fields: Any) -> dict[str, Any]:
    # A device that breaks no rule, with the fields a run changes.
    return {"shop": shop, "home_side": side, "name": "Laptop ya Dawa", "code": 1, "key_hash": HASH, **fields}


@pytest.mark.parametrize(
    ("fields", "rule"),
    [
        pytest.param({"status": "lost"}, "people_device_status_known", id="status_unknown"),
        pytest.param({"name": ""}, "people_device_name_not_blank", id="name_blank"),
        pytest.param({"code": 0}, "people_device_code_given", id="code_zero"),
        # The Done when's "stored hashed", held by the database too: a key stored by mistake is refused.
        pytest.param({"key_hash": A_KEY}, "people_device_key_hashed", id="key_not_hashed"),
        pytest.param({"key_hash": "A" * 64}, "people_device_key_hashed", id="hash_capital_letters"),
    ],
)
def test_database_refuses_a_device_that_breaks_a_rule(
    shop_a: Shop, side_a: Side, fields: dict[str, Any], rule: str
) -> None:
    with shop_context(shop_a), pytest.raises(IntegrityError, match=rule):
        Device.objects.create(**device_row(shop_a, side_a, **fields))


@pytest.mark.parametrize(
    ("fields", "rule"),
    [
        # D7: one code per device in a shop, whatever writes the row.
        pytest.param({"name": "Simu ya Dawa", "key_hash": OTHER_HASH}, "people_device_code_once", id="code_twice"),
        pytest.param(
            {"name": "LAPTOP YA DAWA", "code": 2, "key_hash": OTHER_HASH}, "people_device_name_once", id="name"
        ),
        pytest.param({"name": "Simu ya Dawa", "code": 2}, "people_device_key_once", id="key_twice"),
    ],
)
def test_database_refuses_a_device_that_repeats_another(
    shop_a: Shop, side_a: Side, fields: dict[str, Any], rule: str
) -> None:
    with shop_context(shop_a):
        Device.objects.create(**device_row(shop_a, side_a))
        with pytest.raises(IntegrityError, match=rule):
            Device.objects.create(**device_row(shop_a, side_a, **fields))


def request_row(**fields: Any) -> dict[str, Any]:
    # A waiting request that breaks no rule, with the fields a run changes. No shop: a request has none.
    return {"code": "ABCDEFGH", "expires_at": timezone.now() + timedelta(minutes=10), "key_hash": HASH, **fields}


@pytest.mark.parametrize(
    ("fields", "rule"),
    [
        pytest.param({"code": "abcdefgh"}, "people_pairingrequest_code_shape", id="code_small_letters"),
        pytest.param({"code": "ABCDEFG0"}, "people_pairingrequest_code_shape", id="code_look_alike"),
        pytest.param({"code": "ABCDEFG"}, "people_pairingrequest_code_shape", id="code_too_short"),
        pytest.param({"key_hash": A_KEY}, "people_pairingrequest_key_hashed", id="key_not_hashed"),
        pytest.param(
            {"expires_at": timezone.now() - timedelta(minutes=1)},
            "people_pairingrequest_expires_after_asked",
            id="expires_before_asked",
        ),
        pytest.param({"confirmed_at": timezone.now()}, "people_pairingrequest_confirmed_whole", id="time_no_device"),
    ],
)
def test_database_refuses_a_request_that_breaks_a_rule(fields: dict[str, Any], rule: str) -> None:
    with pytest.raises(IntegrityError, match=rule):
        PairingRequest.objects.create(**request_row(**fields))


def test_database_refuses_a_request_confirmed_without_a_time(shop_a: Shop, side_a: Side) -> None:
    # The other half of confirmed_whole: a device named, but no time it was confirmed.
    with shop_context(shop_a):
        device = Device.objects.create(**device_row(shop_a, side_a))
    with pytest.raises(IntegrityError, match="people_pairingrequest_confirmed_whole"):
        PairingRequest.objects.create(**request_row(device=device))


@pytest.mark.parametrize(
    ("fields", "rule"),
    [
        # Every code ever given stays taken, so a code means one request only.
        pytest.param({"key_hash": OTHER_HASH}, "people_pairingrequest_code_once", id="code_twice"),
        pytest.param({"code": "BCDEFGHJ"}, "people_pairingrequest_key_once", id="key_twice"),
    ],
)
def test_database_refuses_a_request_that_repeats_another(fields: dict[str, Any], rule: str) -> None:
    PairingRequest.objects.create(**request_row())
    with pytest.raises(IntegrityError, match=rule):
        PairingRequest.objects.create(**request_row(**fields))
