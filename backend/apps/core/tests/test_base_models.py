"""apps/core/tests/test_base_models.py — tests for the abstract base models in apps/core/models.py.

They pin down the two promises every table's id makes (ADR-0007): it is a UUID of version 7, and an id
made later sorts later. No database is needed: Django runs `default=uuid.uuid7` when the object is built
in Python, before any save.
"""

import uuid
from collections.abc import Iterator

import pytest
from django.test.utils import isolate_apps

from apps.core.models import TimeStamped, UUIDModel


@pytest.fixture
def thing_model() -> Iterator[type[UUIDModel]]:
    # A throwaway model built on both bases, as every real table will be. isolate_apps registers it in a
    # temporary list of models that is thrown away after the test, so it never becomes a table and
    # makemigrations never sees it: CORE-1 adds no tables.
    with isolate_apps("apps.core"):

        class Thing(UUIDModel, TimeStamped):
            pass

        yield Thing


def test_ids_are_uuid_version_7(thing_model: type[UUIDModel]) -> None:
    thing = thing_model()

    # The id exists before any save: the server knows a sale's id before it writes the sale's lines.
    assert isinstance(thing.id, uuid.UUID)
    assert thing.id.version == 7


def test_ids_sort_by_creation_time(thing_model: type[UUIDModel]) -> None:
    # 1,000 in a row: many are made in the same millisecond, so this also checks the counter uuid7 keeps
    # inside one millisecond, not only the clock. (Two server processes share no counter: their ids are
    # in order only to the millisecond, which is still enough to keep the index fast.)
    ids = [thing_model().id for _ in range(1000)]

    # PostgreSQL sorts uuids byte by byte, the same order Python uses, so this is the order the index
    # sees: each new id goes at its end (ADR-0007).
    assert sorted(ids) == ids
    assert len(set(ids)) == len(ids)  # and no two are the same
