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


def test_more_keys_cover_fewer() -> None:
    # Baba holds every key on every side: he covers Asha, and she doesn't cover him.
    baba = HeldPermissions(every_side=frozenset(Permission))
    asha = HeldPermissions(every_side=WEIGH_EVERYWHERE, on_side={DAWA: SELLER_ON_DAWA})

    assert baba.covers(asha)
    assert not asha.covers(baba)


def test_a_key_on_one_side_does_not_cover_it_on_every_side() -> None:
    # The side counts, not only the code. Meneja weighs on Dawa alone; Juma weighs on every side, a side added later
    # included, so Juma holds more, though both hold the same code.
    meneja = HeldPermissions(on_side={DAWA: WEIGH_EVERYWHERE})
    juma = HeldPermissions(every_side=WEIGH_EVERYWHERE)

    assert not meneja.covers(juma)
    assert juma.covers(meneja)


def test_a_key_on_one_side_does_not_cover_it_on_another() -> None:
    meneja = HeldPermissions(on_side={DAWA: SELLER_ON_DAWA})
    asha = HeldPermissions(on_side={VYAKULA: SELLER_ON_DAWA})

    assert not meneja.covers(asha)


def test_keys_from_a_side_and_from_every_side_add_up() -> None:
    # On Dawa, Meneja holds both codes: one given there, and one on every side. That covers someone given both on Dawa.
    meneja = HeldPermissions(every_side=WEIGH_EVERYWHERE, on_side={DAWA: SELLER_ON_DAWA})
    asha = HeldPermissions(on_side={DAWA: SELLER_ON_DAWA | WEIGH_EVERYWHERE})

    assert meneja.covers(asha)


def test_everyone_covers_someone_with_no_keys() -> None:
    # An emptied role on a side adds nothing to cover. And two people holding the same keys cover each other.
    juma = HeldPermissions(on_side={VYAKULA: frozenset()})

    assert HeldPermissions().covers(juma)
    assert HeldPermissions().covers(HeldPermissions())
    assert juma.covers(juma)
