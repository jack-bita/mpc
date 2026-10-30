"""apps/core/tests/test_held_permissions.py — reading what one person holds, side by side (02 §5, rule X1; PPL-5).

HeldPermissions is the one place the rule is written: on a side, what was given there plus what was given on every
side; on the whole shop, only what was given on every side. A person sees a side when they hold at least one code
there. No database: the value is filled in by `people` (apps/people/permissions.py) and only read here.

    person   given                                   sees
    Baba     Owner, every side                       every side, one added later too
    Asha     Seller on Dawa, stock.count on Vyakula  Dawa and Vyakula
    Juma     nothing, or a role emptied by its owner no side
"""

import uuid

from apps.core.permissions import HeldPermissions, Permission

DAWA = uuid.uuid7()
VYAKULA = uuid.uuid7()

SELLER_ON_DAWA = frozenset({Permission.SALE_WRITE, Permission.SALE_BARGAIN})
WEIGH_EVERYWHERE = frozenset({Permission.STOCK_WEIGH})


def test_a_side_adds_the_every_side_codes() -> None:
    # Asha sells on Dawa and weighs on every side: on Dawa she does both, on Vyakula she only weighs.
    asha = HeldPermissions(every_side=WEIGH_EVERYWHERE, on_side={DAWA: SELLER_ON_DAWA})

    assert asha.on(DAWA) == SELLER_ON_DAWA | WEIGH_EVERYWHERE
    assert asha.on(VYAKULA) == WEIGH_EVERYWHERE


def test_whole_shop_counts_only_every_side_codes() -> None:
    # An action on a row of no side, such as a product, needs the code on every side: a key for Dawa alone opens
    # nothing of the whole shop's (02 §5).
    asha = HeldPermissions(every_side=WEIGH_EVERYWHERE, on_side={DAWA: SELLER_ON_DAWA})

    assert asha.on(None) == WEIGH_EVERYWHERE


def test_a_code_on_every_side_shows_every_side() -> None:
    # None, not a list of today's sides: a side the owner adds tomorrow is seen too, with no new role.
    baba = HeldPermissions(every_side=frozenset(Permission), on_side={})

    assert baba.sides_seen() is None


def test_sides_seen_are_those_with_a_code() -> None:
    asha = HeldPermissions(on_side={DAWA: SELLER_ON_DAWA, VYAKULA: frozenset({Permission.STOCK_COUNT})})

    assert asha.sides_seen() == frozenset({DAWA, VYAKULA})


def test_a_side_with_no_codes_is_not_seen() -> None:
    # A role whose owner took every code out of it still sits on Juma's side: it opens nothing, so he sees nothing.
    juma = HeldPermissions(on_side={VYAKULA: frozenset()})

    assert juma.sides_seen() == frozenset()
    assert juma.on(VYAKULA) == frozenset()


def test_nothing_held_sees_no_side() -> None:
    # What a suspended person, or one who has left, holds (X2).
    nobody = HeldPermissions()

    assert nobody.sides_seen() == frozenset()
    assert nobody.on(DAWA) == frozenset()
    assert nobody.on(None) == frozenset()
