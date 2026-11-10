"""apps/sync/tests/test_registry.py — what a shop's devices keep a copy of, and which fields (SYNC-2; 03 §6.1).

The registry (apps/sync/registry.py) names each table a device keeps a copy of, by its link type code, with the rows a
device gets and the fields it may see:

    code              a device gets                                         not sent
    side              every side of the shop                                —
    payment_account   the accounts in use, each with the sides it serves    an archived account
    staff             the people at work there, suspended ones too          someone who left, or was switched off
    setting           each rule's row in force today, and every later one   a row replaced since

The bootstrap sends them all at once (SYNC-2), and the pull the ones that changed (SYNC-3), both through this one list,
so a device never gets a table or a field it isn't meant to. Nothing secret is on it: test_bootstrap_secrets.py.
Fake data only: the repo is public (03 §10).
"""

import json
from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import Any

import pytest
from rest_framework.renderers import JSONRenderer

from apps.core.changes import record_change, recording_changes
from apps.core.links import table_of
from apps.core.permissions import ROLE_TEMPLATES, Permission, RoleTemplate
from apps.core.settings_registry import CASH_TOLERANCE, IDLE_MINUTES, LATE_FINE, SettingKey
from apps.core.tenancy import ShopMismatch, shop_context, system_context
from apps.people.models import StaffMember, User
from apps.people.selectors import shop_today
from apps.people.services import (
    FIELDS_ON_STAFF_ROWS,
    add_staff,
    change_own_settings,
    grant_permission,
    mark_left,
    set_pin,
    suspend,
)
from apps.shops.models import (
    PaymentAccount,
    PaymentAccountKind,
    PaymentAccountSide,
    PaymentAccountStatus,
    Setting,
    Shop,
    Side,
)
from apps.shops.services import add_side
from apps.sync.api.serializers import StaffRecord
from apps.sync.registry import REGISTRY
from apps.sync.selectors import last_change_number
from tests.change_log import last_line

pytestmark = pytest.mark.django_db

GiveRole = Callable[[StaffMember, RoleTemplate, Side | None], None]


def sent(code: str, shop: Shop) -> list[dict[str, Any]]:
    # What a device of `shop` gets of one table, as the bootstrap sends it: the registry's rows, through its fields, as
    # JSON, which is all a device ever sees: a linked row's id is text there, not a UUID. Read inside the shop, as the
    # device's visit opens it (DeviceView).
    entry = REGISTRY[code]
    with shop_context(shop):
        data = entry.serializer(entry.rows(shop), many=True).data
    rows: list[dict[str, Any]] = json.loads(JSONRenderer().render(data))
    return rows


def hire(shop: Shop, full_name: str, nickname: str) -> StaffMember:
    # A person with a job at the shop, made the way the app makes one (PPL-2).
    user = User.objects.create_user(full_name=full_name)
    with shop_context(shop):
        return add_staff(shop=shop, user=user, display_name=nickname, by=None)


def row_of(staff: StaffMember) -> dict[str, Any]:
    # One person's row, as their shop's devices get it.
    (row,) = [row for row in sent("staff", staff.shop) if row["id"] == str(staff.pk)]
    return row


@pytest.fixture
def dawa(shop_a: Shop) -> Side:
    # A side made the way the app makes one, with its stock location and its cash drawer (SHOP-2).
    with shop_context(shop_a):
        return add_side(shop=shop_a, code="D", name="Dawa", by=None)


@pytest.fixture
def vyakula(shop_a: Shop) -> Side:
    with shop_context(shop_a):
        return add_side(shop=shop_a, code="F", name="Vyakula", by=None)


def test_registry_names_each_table_by_its_link_type_code(shop_a: Shop) -> None:
    # A line of the change log names its table by the same code (apps/core/links.py), so the pull (SYNC-3) finds a
    # line's rows and fields here by it. Sides first: the other tables name them.
    assert list(REGISTRY) == ["side", "payment_account", "staff", "setting"]
    for code, entry in REGISTRY.items():
        assert entry.code == code
        with shop_context(shop_a):
            assert entry.rows(shop_a).model is table_of(code)
        assert entry.serializer.Meta.model is table_of(code)


def test_rows_are_read_only_inside_their_own_shop(shop_a: Shop, shop_b: Shop) -> None:
    # T1: shop B open, shop A asked for. The guard would show B's rows and the shop filter none, so a device would get
    # an empty shop without a word: a bug in the calling code, refused loudly instead.
    for entry in REGISTRY.values():
        with shop_context(shop_b), pytest.raises(ShopMismatch):
            entry.rows(shop_a)


def test_each_list_keeps_to_its_own_shop_with_every_shop_open(
    shop_a: Shop, dawa: Side, staff_a: StaffMember, shop_b: Shop, side_b: Side, staff_b: StaffMember
) -> None:
    # A system job has every shop open (system_context, 03 §5.11), and the guard then shows every shop's rows: each
    # list, and the cursor, must name their shop themselves, or a job that read them for shop A would get shop B's too.
    # Both shops hold a row of every table, and shop B more changes than shop A. Shown red by dropping one list's shop.
    for shop, fine in ((shop_a, "1250.00"), (shop_b, "1750.00")):
        add_row(shop, LATE_FINE, fine, shop_today(shop))
    # Setting the shops up wrote lines too (SYNC-15), so shop A's cursor is counted from where this test starts.
    start_a = last_line(shop_a)
    with shop_context(shop_a), recording_changes(shop_a):
        record_change(dawa)
    for _ in range(3):
        with shop_context(shop_b), recording_changes(shop_b):
            record_change(side_b)
    with system_context():
        for code, entry in REGISTRY.items():
            shops = {row.shop_id for row in entry.rows(shop_a)}
            assert shops == {shop_a.pk}, code  # shop A's rows, and only them
        # Shop B's last number is the higher, so a cursor read across both shops would answer it, not shop A's.
        assert last_line(shop_b) > last_line(shop_a)
        assert last_change_number(shop_a) == start_a + 1


def test_a_shop_with_no_change_is_at_zero(shop_a: Shop) -> None:
    # A shop whose log has no line yet: its cursor is 0, which a pull reads as "from the start", as numbers start at 1
    # (SYNC-1). Every shop the app sets up has lines from its first moment (SYNC-15), so only a bare shop shows it.
    with shop_context(shop_a):
        assert last_change_number(shop_a) == 0


def test_every_side_is_sent(shop_a: Shop, dawa: Side, vyakula: Side) -> None:
    # Both sides, by their letter: a Dawa laptop may sell on Vyakula too, if the person's keys say so (02 §5).
    assert sent("side", shop_a) == [
        {"id": str(dawa.pk), "code": "D", "name": "Dawa", "sale_flow": "one_screen", "is_live": False},
        {"id": str(vyakula.pk), "code": "F", "name": "Vyakula", "sale_flow": "one_screen", "is_live": False},
    ]


def test_accounts_in_use_are_sent_with_the_sides_they_serve(shop_a: Shop, dawa: Side, vyakula: Side) -> None:
    # Each side's drawer came with the side (add_side). A Lipa Namba serves both sides; an old bank account is archived,
    # so no counter offers it any more. Written straight to the tables: no service adds an account yet (MONEY-1).
    with shop_context(shop_a):
        lipa = PaymentAccount.objects.create(
            shop=shop_a, kind=PaymentAccountKind.MOBILE_MONEY, name="Lipa Namba", provider="M-Pesa", number="555123"
        )
        for side in (vyakula, dawa):
            PaymentAccountSide.objects.create(shop=shop_a, account=lipa, side=side)
        PaymentAccount.objects.create(
            shop=shop_a,
            kind=PaymentAccountKind.BANK,
            name="Benki ya Zamani",
            provider="Benki ya Mfano",
            number="0150000000",
            status=PaymentAccountStatus.ARCHIVED,
        )
        drawer = {
            account.name: account for account in PaymentAccount.objects.filter(kind=PaymentAccountKind.CASH_DRAWER)
        }
    assert sent("payment_account", shop_a) == [
        {
            "id": str(drawer["Dawa"].pk),
            "kind": "cash_drawer",
            "name": "Dawa",
            "provider": "",
            "number": "",
            "sides": [str(dawa.pk)],
        },
        {
            "id": str(drawer["Vyakula"].pk),
            "kind": "cash_drawer",
            "name": "Vyakula",
            "provider": "",
            "number": "",
            "sides": [str(vyakula.pk)],
        },
        # Its sides by their letter, D before F, whatever order they were linked in.
        {
            "id": str(lipa.pk),
            "kind": "mobile_money",
            "name": "Lipa Namba",
            "provider": "M-Pesa",
            "number": "555123",
            "sides": [str(dawa.pk), str(vyakula.pk)],
        },
    ]


def test_people_at_work_are_sent_and_people_gone_are_not(
    shop_a: Shop, staff_a: StaffMember, staff_b: StaffMember
) -> None:
    # A to Z by full name. Neema is suspended: still sent, marked so, so an offline laptop refuses her PIN as the
    # server does (X2, SYNC-10). Baraka left, for good, and Zuhura was switched off (User.is_active), until someone
    # switches her on: neither can log in here now, so neither is sent, as the PIN screen shows neither
    # (pin_screen_staff). Shop B's person is never sent.
    asha = hire(shop_a, "Asha Mfano", "Asha")
    neema = hire(shop_a, "Neema Mfano", "Neema")
    baraka = hire(shop_a, "Baraka Mfano", "Baraka")
    zuhura = hire(shop_a, "Zuhura Mfano", "Zuhura")
    with shop_context(shop_a):
        suspend(neema, by=None, reason="Likizo ya adhabu")
        mark_left(baraka, left_on=shop_today(shop_a), by=None, reason="Amehamia mji mwingine")
    zuhura.user.is_active = False
    zuhura.user.save(update_fields=["is_active"])
    assert [(row["id"], row["status"]) for row in sent("staff", shop_a)] == [
        (str(asha.pk), "active"),
        (str(neema.pk), "suspended"),
        (str(staff_a.pk), "active"),
    ]


def test_a_persons_row_holds_what_the_counter_needs(shop_a: Shop) -> None:
    # The names for the PIN screen's tile; when the PIN last changed, so the laptop drops its own check of the old one
    # (SYNC-10); and the person's language and font, so an offline login shows their own screens (UI-9). A photo joins
    # with PPL-4. Exactly these fields: what must never travel is test_bootstrap_secrets.py's.
    asha = hire(shop_a, "Asha Mfano", "Asha")
    with shop_context(shop_a):
        set_pin(asha, "2580", by=None)
    change_own_settings(asha.user, language="en", font="second")
    asha.refresh_from_db()
    row = row_of(asha)
    assert asha.pin_changed_at is not None
    assert datetime.fromisoformat(row.pop("pin_changed_at")) == asha.pin_changed_at
    assert row == {
        "id": str(asha.pk),
        "full_name": "Asha Mfano",
        "display_name": "Asha",
        "status": "active",
        "language": "en",
        "font": "second",
        "permissions": {"every_side": [], "sides": []},
    }


def test_each_persons_keys_are_sent_side_by_side(shop_a: Shop, dawa: Side, vyakula: Side, give_role: GiveRole) -> None:
    # Worked out on the server, as `me` and the office routes read them (HeldPermissions, 02 §5), so the laptop does no
    # role arithmetic: on a side, a person holds what was given on every side plus what was given on that side alone.
    # Asha sells on Dawa. Juma manages every side, and may also change Vyakula's settings, one of the owner's four.
    asha = hire(shop_a, "Asha Mfano", "Asha")
    juma = hire(shop_a, "Juma Mfano", "Juma")
    give_role(asha, RoleTemplate.SELLER, dawa)
    give_role(juma, RoleTemplate.MANAGER, None)
    with shop_context(shop_a):
        grant_permission(juma, Permission.SETTINGS_MANAGE, side=vyakula, by=None)
    assert row_of(asha)["permissions"] == {
        "every_side": [],
        "sides": [{"side": str(dawa.pk), "permissions": sorted(ROLE_TEMPLATES[RoleTemplate.SELLER])}],
    }
    assert row_of(juma)["permissions"] == {
        "every_side": sorted(ROLE_TEMPLATES[RoleTemplate.MANAGER]),
        "sides": [{"side": str(vyakula.pk), "permissions": [Permission.SETTINGS_MANAGE.value]}],
    }


def test_a_suspended_person_is_sent_holding_no_keys(shop_a: Shop, dawa: Side, give_role: GiveRole) -> None:
    # X2: suspended, Neema holds nothing, wherever she was given it, so even a laptop that missed her status couldn't
    # let her sell. Her keys come back with her (unsuspend), on the row sent then.
    neema = hire(shop_a, "Neema Mfano", "Neema")
    give_role(neema, RoleTemplate.SELLER, dawa)
    with shop_context(shop_a):
        suspend(neema, by=None, reason="Likizo ya adhabu")
    row = row_of(neema)
    assert row["status"] == "suspended"
    assert row["permissions"] == {"every_side": [], "sides": []}


def add_row(shop: Shop, key: SettingKey[Any], value: str, effective_from: date, side: Side | None = None) -> Setting:
    # A row written the way the settings screen will write one (SHOP-3): checked, then saved.
    with shop_context(shop):
        row = Setting(shop=shop, side=side, key=key.key, value=value, effective_from=effective_from)
        row.full_clean()
        row.save()
    return row


def test_each_rules_row_in_force_and_every_later_one_are_sent(shop_a: Shop, dawa: Side) -> None:
    # An offline laptop must switch to next week's fine on its day, with no network (03 §5.8), but needs nothing a newer
    # row has replaced. The shop's today is the one the shop's clock reads (02 §1).
    today = shop_today(shop_a)
    add_row(shop_a, LATE_FINE, "800.00", today - timedelta(days=60))  # replaced by the next row: not sent
    fine_now = add_row(shop_a, LATE_FINE, "1000.00", today - timedelta(days=10))
    # Next week's fine, typed wrong, then fixed with one more row for the same day: the row written last wins (T2).
    add_row(shop_a, LATE_FINE, "15000.00", today + timedelta(days=7))
    fine_next_week = add_row(shop_a, LATE_FINE, "1500.00", today + timedelta(days=7))
    fine_next_month = add_row(shop_a, LATE_FINE, "2000.00", today + timedelta(days=30))
    # A row that starts today is in force today.
    idle_today = add_row(shop_a, IDLE_MINUTES, "20", today)
    # A side's own row beats the shop's (02 §4): Dawa's, though older, stays in force on Dawa.
    tolerance_dawa = add_row(shop_a, CASH_TOLERANCE, "200.00", today - timedelta(days=100), side=dawa)
    tolerance_shop = add_row(shop_a, CASH_TOLERANCE, "500.00", today - timedelta(days=5))
    with shop_context(shop_a):
        # Two rows get_setting never reads, written past full_clean as only a bug could: a side's row of a rule kept
        # for the whole shop, and a rule no longer in the list in core.
        Setting.objects.create(shop=shop_a, side=dawa, key=LATE_FINE.key, value="1.00", effective_from=today)
        Setting.objects.create(shop=shop_a, key="zamani.kanuni", value="1", effective_from=today)
    # By rule, then by day; a side's row beside the shop's, by its own day.
    assert [row["id"] for row in sent("setting", shop_a)] == [
        str(fine_now.pk),
        str(fine_next_week.pk),
        str(fine_next_month.pk),
        str(tolerance_dawa.pk),
        str(tolerance_shop.pk),
        str(idle_today.pk),
    ]
    assert sent("setting", shop_a)[3] == {
        "id": str(tolerance_dawa.pk),
        "key": "cash.tolerance",
        "side": str(dawa.pk),
        "value": "200.00",
        "effective_from": str(today - timedelta(days=100)),
    }


def test_the_people_app_knows_which_of_a_persons_fields_travel() -> None:
    # A change to the person (User), who belongs to no shop, writes a staff line in each of their shops only when it
    # touches a field the staff row shows, or whether they are sent at all (FIELDS_ON_STAFF_ROWS,
    # apps/people/services.py). `people` can't read this registry (a lower layer), so the list is written there, and
    # pinned here: a person's field added to StaffRecord, a photo say, turns this red until the list names it too.
    sources = [field.source or "" for field in StaffRecord().fields.values()]
    from_the_person = {source.removeprefix("user.") for source in sources if source.startswith("user.")}
    # And is_active: staff_rows sends only the people switched on.
    assert from_the_person | {"is_active"} == FIELDS_ON_STAFF_ROWS
