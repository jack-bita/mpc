"""apps/shops/tests/test_sides.py — the rules of a shop's sides, stock locations and payment accounts (02 §4).

A side is a section of one shop (ADR-0001): MPC has a Drugs side and a Foods side, each with its own
stock, cash drawer, staff roles and debts. A side's stock sits in stock locations (ADR-0002): R1 has one
default location per side, which the screens never show. A payment account is where money lands: a cash
drawer, a Lipa Namba or a bank account, each serving one or more sides.

    shop    side          stock location     payment accounts
    MFANO   Dawa (D)      Dawa (default)     cash drawer "Dawa"     ─┐
    MFANO   Vyakula (F)   Vyakula (default)  cash drawer "Vyakula"   ├─ one Lipa Namba serves both sides
                                                                    ─┘

All four tables are ShopScoped (CORE-2): their rows are read and checked through the guarded `objects`,
so every test works inside `shop_context(shop)`, as a visit will. Each test names one rule; most rules
are the database's own too, the last guard (03 §5.6).
"""

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from apps.core.tenancy import shop_context
from apps.shops.models import PaymentAccount, PaymentAccountSide, SaleFlow, Shop, Side, StockLocation

pytestmark = pytest.mark.django_db

# Fake data only: the repo is public (03 §10). Side names as a shop would type them.
DAWA = {"code": "D", "name": "Dawa"}
# A made-up Lipa Namba: a real shop's number never enters the repo (rule 10).
LIPA_NAMBA = {"kind": "mobile_money", "name": "Lipa Namba", "provider": "M-Pesa", "number": "123456"}


def test_side_code_unique_within_shop(shop_a: Shop, shop_b: Shop) -> None:
    # The side's letter starts every human number made on its devices, like D2-0457 (D7). Two sides with
    # the same letter would print the same numbers, so a shop can't have two D's. Another shop has its
    # own D: the letter is unique within a shop only.
    with shop_context(shop_b):
        Side.objects.create(shop=shop_b, **DAWA)

    with shop_context(shop_a):
        Side.objects.create(shop=shop_a, **DAWA)
        second = Side(shop=shop_a, code="D", name="Dawa Nyingine")
        # The way a form checks a new side (full_clean): the clash comes back as a code (ADR-0032).
        with pytest.raises(ValidationError) as refused:
            second.full_clean()
        assert [error.code for error in refused.value.error_dict["__all__"]] == ["side.code_taken"]
        # And code that skips full_clean meets the database's own rule. Last: after a refused write,
        # PostgreSQL runs no more queries in this test's transaction.
        with pytest.raises(IntegrityError, match="shops_side_code_unique"):
            second.save()


def test_side_starts_switched_off(shop_a: Shop) -> None:
    # Each side is switched on in settings once the owner agrees (ADR-0033, SHOP-3). A side that started
    # on would reach the counters before anyone chose it. One screen is the simple way to sell; Foods
    # chooses the writer → cashier → loader flow when its side is made.
    with shop_context(shop_a):
        side = Side.objects.create(shop=shop_a, **DAWA)
        side.refresh_from_db()

    assert side.is_live is False
    assert side.sale_flow == SaleFlow.ONE_SCREEN


def test_side_code_stored_as_a_capital(shop_a: Shop) -> None:
    # Typed as a small letter, it is cleaned first, the way a form checks a side (full_clean). So "d"
    # can never sit beside "D" as a second side with the same letter.
    with shop_context(shop_a):
        side = Side(shop=shop_a, code="d", name="Dawa")
        side.full_clean()
        side.save()
        side.refresh_from_db()

    assert side.code == "D"


def test_side_name_of_only_spaces_refused(shop_a: Shop) -> None:
    # A form trims spaces before the model sees them, but code that calls full_clean itself, like
    # create_shop, gets no form. Trimmed by the model, a name of only spaces is "", and the not-blank rule
    # refuses it with its code, instead of storing a side that looks empty on every screen.
    with shop_context(shop_a):
        side = Side(shop=shop_a, code="D", name="   ")
        with pytest.raises(ValidationError) as refused:
            side.full_clean()

    assert [error.code for error in refused.value.error_dict["__all__"]] == ["side.name_blank"]


@pytest.mark.parametrize(
    ("fields", "rule"),
    [
        # Code that saves directly skips the cleaning in full_clean, so these reach the database as typed.
        pytest.param({"code": "d"}, "shops_side_code_one_capital_letter", id="code_small_letter"),
        pytest.param({"code": "1"}, "shops_side_code_one_capital_letter", id="code_digit"),
        pytest.param({"code": ""}, "shops_side_code_one_capital_letter", id="code_blank"),
        pytest.param({"sale_flow": "phone"}, "shops_side_sale_flow_known", id="sale_flow_unknown"),
        pytest.param({"name": ""}, "shops_side_name_not_blank", id="name_blank"),
    ],
)
def test_database_refuses_a_side_that_breaks_a_rule(shop_a: Shop, fields: dict[str, object], rule: str) -> None:
    # One run per rule in Side.Meta, and each run names the rule it expects: a refusal by another rule
    # would hide a broken one.
    with shop_context(shop_a), pytest.raises(IntegrityError, match=rule):
        Side.objects.create(shop=shop_a, **{**DAWA, **fields})


def test_one_default_location_per_side(shop_a: Shop) -> None:
    # ADR-0002: stock is kept per location, and R1 has exactly one per side, the default. A second
    # location is allowed (a store room, later), but a second default would leave "where does this
    # side's stock go?" with two answers.
    with shop_context(shop_a):
        side = Side.objects.create(shop=shop_a, **DAWA)
        StockLocation.objects.create(shop=shop_a, side=side, name="Dawa", is_default=True)
        StockLocation.objects.create(shop=shop_a, side=side, name="Stoo")
        second_default = StockLocation(shop=shop_a, side=side, name="Stoo ya Pili", is_default=True)

        with pytest.raises(ValidationError) as refused:
            second_default.full_clean()
        assert [error.code for error in refused.value.error_dict["__all__"]] == ["location.default_taken"]
        with pytest.raises(IntegrityError, match="shops_stocklocation_one_default_per_side"):
            second_default.save()


def test_database_refuses_a_location_without_a_name(shop_a: Shop) -> None:
    with shop_context(shop_a):
        side = Side.objects.create(shop=shop_a, **DAWA)
        with pytest.raises(IntegrityError, match="shops_stocklocation_name_not_blank"):
            StockLocation.objects.create(shop=shop_a, side=side, name="", is_default=True)


def test_one_lipa_namba_serves_both_sides(shop_a: Shop) -> None:
    # 02 §4: MPC has one Lipa Namba for both sides; each payment still records its side. So an account
    # can serve several sides, through its links.
    with shop_context(shop_a):
        dawa = Side.objects.create(shop=shop_a, **DAWA)
        vyakula = Side.objects.create(shop=shop_a, code="F", name="Vyakula")
        lipa = PaymentAccount.objects.create(shop=shop_a, **LIPA_NAMBA)
        PaymentAccountSide.objects.create(shop=shop_a, account=lipa, side=dawa)
        PaymentAccountSide.objects.create(shop=shop_a, account=lipa, side=vyakula)

        assert sorted(side.code for side in lipa.sides.all()) == ["D", "F"]


def test_account_serves_a_side_once(shop_a: Shop) -> None:
    # A second link to the same side would count that side twice in any total built from the links.
    with shop_context(shop_a):
        side = Side.objects.create(shop=shop_a, **DAWA)
        lipa = PaymentAccount.objects.create(shop=shop_a, **LIPA_NAMBA)
        PaymentAccountSide.objects.create(shop=shop_a, account=lipa, side=side)
        second = PaymentAccountSide(shop=shop_a, account=lipa, side=side)

        with pytest.raises(ValidationError) as refused:
            second.full_clean()
        assert [error.code for error in refused.value.error_dict["__all__"]] == ["payment_account.side_taken"]
        with pytest.raises(IntegrityError, match="shops_paymentaccountside_once"):
            second.save()


def test_new_account_is_active(shop_a: Shop) -> None:
    # Nothing is deleted (rule 7): an account the shop stops using is archived, never removed.
    with shop_context(shop_a):
        lipa = PaymentAccount.objects.create(shop=shop_a, **LIPA_NAMBA)
        lipa.refresh_from_db()

    assert lipa.status == "active"


@pytest.mark.parametrize(
    ("fields", "rule"),
    [
        pytest.param({"kind": "cheque"}, "shops_paymentaccount_kind_known", id="kind_unknown"),
        pytest.param({"status": "closed"}, "shops_paymentaccount_status_known", id="status_unknown"),
        pytest.param({"name": ""}, "shops_paymentaccount_name_not_blank", id="name_blank"),
        # A cash drawer is a box under the counter: no network, no number.
        pytest.param({"kind": "cash_drawer"}, "shops_paymentaccount_details_match_kind", id="drawer_with_a_number"),
        # A Lipa Namba or a bank account is nothing without its number and who runs it.
        pytest.param({"number": ""}, "shops_paymentaccount_details_match_kind", id="lipa_namba_without_number"),
        pytest.param(
            {"kind": "bank", "provider": ""}, "shops_paymentaccount_details_match_kind", id="bank_without_provider"
        ),
    ],
)
def test_database_refuses_an_account_that_breaks_a_rule(shop_a: Shop, fields: dict[str, object], rule: str) -> None:
    # Each run starts from a valid Lipa Namba and breaks one rule in PaymentAccount.Meta.
    with shop_context(shop_a), pytest.raises(IntegrityError, match=rule):
        PaymentAccount.objects.create(shop=shop_a, **{**LIPA_NAMBA, **fields})
