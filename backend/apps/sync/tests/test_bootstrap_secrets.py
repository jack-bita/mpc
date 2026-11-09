"""apps/sync/tests/test_bootstrap_secrets.py — nothing secret leaves the server for a shop's devices (SYNC-2; 03 §6.1,
the sync rules).

A shared laptop's copy of the shop is open to whoever uses the laptop next: Juma, at the Dawa counter, could read every
byte of it. So these never travel:

    never sent                     why
    a PIN's hash                   a copy of it can be guessed offline, 10,000 PINs at most (03 §5.9)
    a password's hash              the same, for the owner's and managers' own logins
    the device's key, or its hash  the key is the laptop's login; its hash finds the device (AUTH-1, AUTH-2)
    a phone, an email              a person's own, not the next person's at the laptop (UI-4)
    a buying price                 not every seller may see it (02 §7); no table holds one yet, so the names catch it

Three checks. The bootstrap's answer, as sent, holds none of a real person's secrets, and no name in it looks secret.
Every field the registry sends is checked by its name, by what it reads, and by what it shows of a linked row, in every
field it holds inside it too (a list's items, a dict's values, a nested record), so a field named innocently but reading
`user.password`, or a product's batches shown by their `unit_cost`, is caught too. And the check catches a secret
planted each of those ways, so it can't quietly stop working. A field that looks secret travels only by a decision
written on its card (TRAVELS_BY_DECISION). Fake data only: the repo is public (03 §10).
"""

import json
import re
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from rest_framework import serializers
from rest_framework.test import APIClient

from apps.core.permissions import RoleTemplate
from apps.core.tenancy import shop_context
from apps.people.models import Device, StaffMember, User
from apps.people.services import add_staff, confirm_pairing, set_pin, start_pairing
from apps.shops.models import Shop, Side
from apps.shops.services import add_side
from apps.sync.registry import REGISTRY

pytestmark = pytest.mark.django_db

GiveRole = Callable[[StaffMember, RoleTemplate, Side | None], None]

# The route and the cookie's name, written out: a promise to the app and to the browser (test_bootstrap.py says why).
BOOTSTRAP = "/api/sync/v1/bootstrap/"
KEY_COOKIE = "device_key"

# A word that marks a secret, as a whole word of a name, plural too: `pin_hash`, `password`, `unit_cost`, `phones`,
# never `monkey` or `costume`. The same idea as SECRET_COLUMN (backend/tests/test_edit_history.py), with a seller's
# secrets added: what a sale cost the shop (cost, buying, profit, margin: `cost.view`'s, 02 §5), a phone and an email;
# and `key` kept apart, below.
SECRET_WORD = re.compile(r"(^|_)(hash|password|secret|token|pepper|cost|buying|profit|margin|phone|email)(e?s)?(_|$)")
# `key` alone is a rule's name in the list in core ("attendance.late_fine"), which a setting's row must carry. Inside a
# longer name it marks a secret: `key_hash`, `api_key`.
KEY_WORD = re.compile(r"(^|_)key(_|$)")

# A field that looks secret but travels all the same, by a decision written on its card, as "table.field" → that
# decision: a customer's phone, say, once the contacts card decides the counter needs it to find someone. Empty today.
# Grown only by such a decision, never to let a test pass, as the sweep's lists are (backend/tests/sweep_lists.py); each
# one must still be found, so a name that went stays off the list.
TRAVELS_BY_DECISION: dict[str, str] = {}


def looks_secret(name: str) -> bool:
    # Whether a field's name, one part of what it reads, or what it shows of a linked row, names a secret.
    return bool(SECRET_WORD.search(name)) or (name != "key" and bool(KEY_WORD.search(name)))


def secret_fields(serializer: serializers.BaseSerializer[Any], path: str = "") -> list[str]:
    # Every field of `serializer` that looks secret, as "staff.pin_hash: its name". `.fields` binds each field, which
    # sets its source: its own name unless it names another, such as "user.full_name".
    assert isinstance(serializer, serializers.Serializer)
    found = []
    for name, field in serializer.fields.items():
        found += _secrets_of(field, f"{path}{name}", name)
    return found


def _secrets_of(field: serializers.Field[Any, Any, Any, Any], where: str, name: str) -> list[str]:
    # One field, and every field it holds inside it, all reported under its own path: a device stores them as one.
    found = []
    if looks_secret(name):
        found.append(f"{where}: its name")
    # What it reads: "user.password" under the innocent name `nickname`. A field held inside another reads nothing of
    # its own (its source is empty); "*" is the whole row, as a method field reads it.
    if field.source and any(looks_secret(part) for part in field.source.split(".")):
        found.append(f"{where}: reads {field.source}")
    # What it shows of each linked row: a product's batches, shown by their `unit_cost` (a SlugRelatedField).
    slug_field = getattr(field, "slug_field", None)
    if slug_field and looks_secret(slug_field):
        found.append(f"{where}: shows {slug_field}")
    # A nested record: its own fields, one level down.
    if isinstance(field, serializers.Serializer):
        found += secret_fields(field, f"{where}.")
    # What a field holds inside it, with no name of its own: a list of records' record, a list's or a dict's item, a
    # many-link's link.
    if isinstance(field, serializers.ListSerializer | serializers.ListField | serializers.DictField):
        # Never empty once bound (a ListField with no child of its own gets a plain one); its type stubs allow None.
        assert field.child is not None
        found += _secrets_of(field.child, where, "")
    if isinstance(field, serializers.ManyRelatedField):
        found += _secrets_of(field.child_relation, where, "")
    return found


def names_in(value: object, path: str = "") -> Iterator[str]:
    # The path of every key of every object in a JSON answer, however deep, as "staff.permissions.every_side": the
    # names a device would store. A list adds nothing to the path: its items are rows of the same table.
    if isinstance(value, dict):
        for name, inner in value.items():
            yield f"{path}{name}"
            yield from names_in(inner, f"{path}{name}.")
    elif isinstance(value, list):
        for item in value:
            yield from names_in(item, path)


def not_decided(paths: Iterator[str] | list[str]) -> list[str]:
    # The findings, or the paths, that no decision lets travel.
    return [path for path in paths if path.split(":")[0] not in TRAVELS_BY_DECISION]


@pytest.fixture
def dawa(shop_a: Shop) -> Side:
    with shop_context(shop_a):
        return add_side(shop=shop_a, code="D", name="Dawa", by=None)


@pytest.fixture
def paired(staff_a2: StaffMember, dawa: Side, give_role: GiveRole) -> tuple[Device, str]:
    # A Dawa laptop, confirmed by a manager the way the app pairs one; its key is the laptop's login.
    give_role(staff_a2, RoleTemplate.MANAGER, None)
    asked = start_pairing()
    with shop_context(staff_a2.shop_id):
        device = confirm_pairing(asked.request.code, name="Laptop ya Dawa", home_side=dawa, by=staff_a2)
    return device, asked.key


def test_bootstrap_never_sends_costs_or_pins(shop_a: Shop, paired: tuple[Device, str], give_role: GiveRole) -> None:
    # Done when: a test proves that no buying price, PIN hash or password ever leaves the server. Asha has every secret
    # a person can have here, and sells on every side, so her row is sent whole, keys and all.
    user = User.objects.create_user(
        full_name="Asha Mfano", phone="+255712345678", email="asha@example.com", password="siri-ya-mfano-2026"
    )
    with shop_context(shop_a):
        asha = add_staff(shop=shop_a, user=user, display_name="Asha", by=None)
        set_pin(asha, "2580", by=None)
    give_role(asha, RoleTemplate.SELLER, None)
    asha.refresh_from_db()
    user.refresh_from_db()
    device, key = paired
    browser = APIClient()
    browser.cookies[KEY_COOKIE] = key
    response = browser.get(BOOTSTRAP)
    assert response.status_code == 200
    # Her row is there: the check below looks at a copy that holds her, not an empty one.
    assert str(asha.pk) in [person["id"] for person in response.json()["staff"]]
    sent = response.content.decode()
    secrets = {
        "the PIN's hash": asha.pin_hash,
        "the password's hash": user.password,
        "the phone": "+255712345678",
        "the email": "asha@example.com",
        "the device's key": key,
        "the device key's hash": device.key_hash,
    }
    assert all(secrets.values())  # each one really set, or the check proves nothing
    assert [what for what, secret in secrets.items() if secret in sent] == []
    names = [path for path in names_in(json.loads(sent)) if looks_secret(path.split(".")[-1])]
    assert not_decided(names) == []


def test_no_registry_field_reads_a_secret() -> None:
    # Every field each table sends, and every field it holds inside it, by its name, by what it reads and by what it
    # shows of a linked row: a field a later card adds, a product's `cost_price` above all (CAT-1), turns this red until
    # its card decides it travels (TRAVELS_BY_DECISION).
    found = [finding for code, entry in REGISTRY.items() for finding in secret_fields(entry.serializer(), f"{code}.")]
    assert not_decided(found) == []
    # A decision for a field that no longer looks secret, or is no longer sent, is stale: it goes from the list.
    assert set(TRAVELS_BY_DECISION) <= {finding.split(":")[0] for finding in found}


class _Inner(serializers.Serializer[Any]):
    # A record held inside another, with a secret of its own.
    api_key = serializers.CharField()


class _Planted(serializers.Serializer[Any]):
    # A made-up table's fields, with a secret planted every way the check must find one.
    pin_hash = serializers.CharField()  # by its name
    nickname = serializers.CharField(source="user.password")  # by what it reads, under an innocent name
    unit_costs = serializers.ListField(child=serializers.CharField())  # by a plural
    extras = _Inner(many=True)  # in a list of nested records
    profit_margin = serializers.CharField()  # by the words of what a sale cost the shop
    # By what a link shows of its row, alone and in a many-link.
    owner = serializers.SlugRelatedField[Any](source="user", slug_field="password", read_only=True)
    batches = serializers.SlugRelatedField[Any](many=True, slug_field="unit_cost", read_only=True)
    wrapped = serializers.ListField(child=_Inner())  # in a list's item
    # In a dict's value.
    notes = serializers.DictField(child=serializers.SlugRelatedField[Any](slug_field="pin_hash", read_only=True))
    # Allowed: a rule's name, when the PIN last changed, and words that only hold a secret word's letters.
    key = serializers.CharField()
    pin_changed_at = serializers.DateTimeField()
    costume = serializers.CharField()
    setting_keys = serializers.CharField()


def test_secret_check_finds_what_it_must() -> None:
    assert secret_fields(_Planted()) == [
        "pin_hash: its name",
        "pin_hash: reads pin_hash",
        "nickname: reads user.password",
        "unit_costs: its name",
        "unit_costs: reads unit_costs",
        "extras.api_key: its name",
        "extras.api_key: reads api_key",
        "profit_margin: its name",
        "profit_margin: reads profit_margin",
        "owner: shows password",
        "batches: shows unit_cost",
        "wrapped.api_key: its name",
        "wrapped.api_key: reads api_key",
        "notes: shows pin_hash",
    ]
