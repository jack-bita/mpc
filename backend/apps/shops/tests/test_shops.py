"""apps/shops/tests/test_shops.py — the rules every shop follows (02 §4, ADR-0014).

A shop is one business: the tenant that every other table will point at (ADR-0022). MPC is a live
shop, the public demo is a demo shop, and a practice shop [R2] is a copy where new workers learn
without touching real money. Each test names one rule the Shop table must keep; the database is the
last guard for each of them (03 §5.6).
"""

from typing import Any

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from apps.shops.models import Shop

pytestmark = pytest.mark.django_db

# Fake shops only: the repo is public (03 §10).
NAME = "Duka la Mfano"
CODE = "MFANO"


def test_new_shop_gets_the_tanzanian_defaults() -> None:
    # Only a name and a code are needed: everything else starts at what a shop in Tanzania uses.
    shop = Shop.objects.create(name=NAME, code=CODE)

    # Read it back from the database: the defaults must be what was really stored.
    shop.refresh_from_db()
    assert shop.timezone == "Africa/Dar_es_Salaam"
    assert shop.currency == "TZS"
    assert shop.default_language == "sw"
    assert shop.kind == "live"
    assert shop.status == "active"
    assert shop.practice_of is None


def test_shop_kind_must_be_known() -> None:
    # Live, demo or practice and nothing else (ADR-0014): the demo seed refuses to touch a live shop
    # (ADR-0029), so code that asks "what kind is this?" must never meet a kind it doesn't know.
    # The database refuses one, even from code that skips every form.
    with pytest.raises(IntegrityError, match="shops_shop_kind_known"):
        Shop.objects.create(name=NAME, code=CODE, kind="training")


def test_shop_status_must_be_known() -> None:
    # Active or suspended and nothing else: a third status that no check knows about could let a
    # suspended shop work as if it were active.
    with pytest.raises(IntegrityError, match="shops_shop_status_known"):
        Shop.objects.create(name=NAME, code=CODE, status="closed")


def test_shop_code_unique() -> None:
    Shop.objects.create(name=NAME, code=CODE)

    # The code is how people tell shops apart (MPC, DEMO), so it must point at one shop only. The
    # database refuses a second one even from code that skips every form: the rule named in Shop.Meta.
    with pytest.raises(IntegrityError, match="shops_shop_code_unique"):
        Shop.objects.create(name="Duka Jingine", code=CODE)


def test_shop_code_taken_has_its_own_code() -> None:
    # The way a form or create_shop checks a new shop (full_clean): the clash comes back as our own
    # code, which the app translates (ADR-0032), not Django's generic `unique`, which says nothing about
    # which rule was broken. Filed under "__all__", the whole record, as SHOP-2's side letters are.
    Shop.objects.create(name=NAME, code=CODE)
    second = Shop(name="Duka Jingine", code=CODE)

    with pytest.raises(ValidationError) as refused:
        second.full_clean()

    assert [error.code for error in refused.value.error_dict["__all__"]] == ["shop.code_taken"]


def test_shop_code_stored_in_capitals() -> None:
    # A code is a few capital letters, the short form people already say: MPC for Mabatini Pumba
    # Center (Jack, 26 Oct 2026). Typed in small letters or with spaces around it, it is cleaned
    # first, the way the admin's form checks a shop (full_clean). So "mfano" can never become a
    # second shop beside "MFANO".
    shop = Shop(name=NAME, code=" mfano ")
    shop.full_clean()
    shop.save()

    shop.refresh_from_db()
    assert shop.code == "MFANO"


def test_practice_shop_points_at_its_live_shop() -> None:
    # ADR-0014: practice mode is a separate shop that names the live shop it copies. Its fake sales
    # belong to another shop, so they can never mix with the real money.
    live = Shop.objects.create(name=NAME, code=CODE)
    practice = Shop.objects.create(name="Duka la Mazoezi", code="MAZOEZI", kind="practice", practice_of=live)

    assert list(live.practice_shops.all()) == [practice]


@pytest.mark.parametrize("kind", ["demo", "practice"])
def test_practice_shop_copies_only_a_live_shop(kind: str) -> None:
    # ADR-0014: practice is a copy of the live shop, where new workers learn the real products. A copy
    # of the demo shop, or of another practice copy, would teach them a shop that doesn't exist. The
    # database can't see another row's kind, so the field's own check does it, in every form (full_clean).
    live = Shop.objects.create(name=NAME, code=CODE)
    other = Shop.objects.create(
        name="Duka Jingine", code="JINGINE", kind=kind, practice_of=live if kind == "practice" else None
    )
    copy = Shop(name="Duka la Mazoezi", code="MAZOEZI", kind="practice", practice_of=other)

    with pytest.raises(ValidationError) as refused:
        copy.full_clean()

    # Under the field's name, so the admin shows it beside the drop-down.
    assert "practice_of" in refused.value.error_dict


def test_only_a_practice_shop_points_at_another_shop() -> None:
    # The other half of the rule: a live or demo shop is nobody's copy. One that named another shop
    # would look like practice to any code that follows `practice_of`.
    live = Shop.objects.create(name=NAME, code=CODE)

    with pytest.raises(IntegrityError, match="shops_shop_only_practice_names_a_shop"):
        Shop.objects.create(name="Duka Jingine", code="JINGINE", practice_of=live)


def test_shop_cannot_practise_on_itself() -> None:
    # A practice shop that named itself would pass the rule above (it is a practice shop with a
    # `practice_of`), so this needs a rule of its own. The id is made in Python before the save
    # (CORE-1), so a shop can point at itself before it is stored.
    shop = Shop(name=NAME, code=CODE, kind="practice")
    shop.practice_of_id = shop.id

    with pytest.raises(IntegrityError, match="shops_shop_not_practice_of_itself"):
        shop.save()


def test_timezone_must_be_real() -> None:
    # Each shop's business dates are worked out in its own timezone (02 §1), so a misspelt one would
    # put every sale on a wrong day. Arusha has no zone of its own: Tanzania is Africa/Dar_es_Salaam.
    # The database doesn't know the list of zones, so the model's checks (full_clean) do it.
    shop = Shop(name=NAME, code=CODE, timezone="Africa/Arusha")

    with pytest.raises(ValidationError) as refused:
        shop.full_clean()

    # Under the field's name, so the form shows it beside the box, and as a code (ADR-0032).
    assert refused.value.error_dict["timezone"][0].code == "shop.timezone_unknown"


@pytest.mark.parametrize(("timezone", "code"), [(None, "null"), ("", "blank")])
def test_missing_timezone_is_reported_not_a_crash(timezone: Any, code: str) -> None:
    # `Any`: None is a value the field's type doesn't allow, which is the point of this test.
    # full_clean runs clean() even after a field has failed its own check, so clean() must not trip over
    # a missing value. The field reports it once, under its name: no crash, and no second error.
    shop = Shop(name=NAME, code=CODE, timezone=timezone)

    with pytest.raises(ValidationError) as refused:
        shop.full_clean()

    assert [error.code for error in refused.value.error_dict["timezone"]] == [code]


@pytest.mark.parametrize(
    ("fields", "rule"),
    [
        # Code that saves directly skips the cleaning in full_clean, so these reach the database as typed.
        pytest.param({"code": "mfano"}, "shops_shop_code_capital_letters", id="code_small_letters"),
        pytest.param({"code": "MPC2"}, "shops_shop_code_capital_letters", id="code_with_a_digit"),
        pytest.param({"code": "M"}, "shops_shop_code_capital_letters", id="code_one_letter"),
        pytest.param({"code": "MF NO"}, "shops_shop_code_capital_letters", id="code_with_a_space"),
        pytest.param({"currency": "tzs"}, "shops_shop_currency_three_capitals", id="currency_three_capitals"),
        pytest.param({"default_language": "fr"}, "shops_shop_language_known", id="language_known"),
        pytest.param({"kind": "practice"}, "shops_shop_practice_names_its_shop", id="practice_shop_names_its_shop"),
    ],
)
def test_database_refuses_a_row_that_breaks_a_rule(fields: dict[str, object], rule: str) -> None:
    # The database is the last guard (03 §5.6): code that skips the admin's form and saves a Shop
    # directly still can't store one that breaks a rule in Shop.Meta. One run per rule. Eight rules
    # guard this table, so each run names the rule it expects: a refusal by another rule would hide
    # a broken one.
    with pytest.raises(IntegrityError, match=rule):
        Shop.objects.create(**{"name": NAME, "code": CODE, **fields})


def test_broken_rule_comes_back_as_a_code() -> None:
    # The way a form checks a shop (full_clean): a rule that spans two fields comes back under
    # `__all__`, with its code, which the screens translate (ADR-0032).
    shop = Shop(name=NAME, code=CODE, kind="practice")

    with pytest.raises(ValidationError) as refused:
        shop.full_clean()

    assert [error.code for error in refused.value.error_dict["__all__"]] == ["shop.practice_needs_shop"]
