"""backend/tests/test_caches.py — every database test starts with empty caches (backend/conftest.py, AUTH-5).

The pairing limits count in database caches, tables that `createcachetable` makes, not models (CACHES,
config/settings/base.py). A test marked `transaction=True` really commits, and Django's clean-up after it empties the
models' tables only: a count it left in a cache would make a later test's limit come early, a failure that depends on
which tests ran before. pytest-django runs every committing test after the others, in the order of their files, so the
count can reach only a committing test that comes later: the two below, in this order. The first leaves a count
behind for good, and the second must not find it.
"""

import pytest
from django.conf import settings
from django.core.cache import caches


@pytest.mark.django_db(transaction=True)
def test_a_committing_test_leaves_a_count_behind() -> None:
    for name in settings.CACHES:
        caches[name].set("left-behind", 1, timeout=3600)


@pytest.mark.django_db(transaction=True)
def test_the_next_test_finds_no_count() -> None:
    assert [name for name in settings.CACHES if caches[name].get("left-behind") is not None] == []
