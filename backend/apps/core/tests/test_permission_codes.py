"""apps/core/tests/test_permission_codes.py — the permission codes, and the six role templates built from them
(02 §5, 03 §5.8).

The codes are stored in roles and grants (apps/people/models.py), so each must fit the column and the shape the
database checks; and every template may name only codes from the list, the Owner's every one of them.
"""

import re

from apps.core.permissions import (
    PERMISSION_CODE_MAX_LENGTH,
    PERMISSION_CODE_SHAPE,
    ROLE_TEMPLATES,
    Permission,
    RoleTemplate,
)


def test_every_code_fits_where_it_is_stored() -> None:
    # "area.action", small letters and underscores, as 02 §5 writes them: sale.bargain, stock.count_approve. A code
    # too long for the column would be refused only when the first role holding it is saved, in a new shop.
    for code in Permission:
        assert re.fullmatch(PERMISSION_CODE_SHAPE, code), code
        assert len(code) <= PERMISSION_CODE_MAX_LENGTH, code


def test_every_template_names_known_codes() -> None:
    # Each of the six templates has its bundle, made of codes from the list only: a misspelt code ("sale.bargin")
    # would give nobody anything, and nobody would notice until a person was refused at the counter.
    assert set(ROLE_TEMPLATES) == set(RoleTemplate)
    for template, codes in ROLE_TEMPLATES.items():
        assert codes, template
        assert codes <= set(Permission), template


def test_owner_template_holds_every_code() -> None:
    # The owner may do everything, on every side (spec §6), including the actions a later card adds: so the Owner's
    # bundle is the whole list, not a copy of it typed out.
    assert ROLE_TEMPLATES[RoleTemplate.OWNER] == set(Permission)


def test_everyone_may_weigh_what_arrives() -> None:
    # Jack (29 Oct 2026): weighing goods as they arrive is everyone's job, so stock.weigh is on every template; the
    # buying price stays with stock.receive, which only the owner and managers hold.
    for template, codes in ROLE_TEMPLATES.items():
        assert Permission.STOCK_WEIGH in codes, template
        assert (Permission.STOCK_RECEIVE in codes) == (template in {RoleTemplate.OWNER, RoleTemplate.MANAGER}), template


def test_manager_holds_all_but_the_owners_four() -> None:
    # Jack (29 Oct 2026): the owner keeps the day's final approval, the pay, the shop's rules and who works there; a
    # manager runs everything else when the owner is away.
    owners_four = {
        Permission.DRAWER_APPROVE,
        Permission.PAY_APPROVE,
        Permission.SETTINGS_MANAGE,
        Permission.STAFF_MANAGE,
    }
    assert ROLE_TEMPLATES[RoleTemplate.MANAGER] == set(Permission) - owners_four
