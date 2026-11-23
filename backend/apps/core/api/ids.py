"""apps/core/api/ids.py — the checks on an id a client makes for a new row (ADR-0007).

A client makes each new row's id itself, so that a retry can be told apart from a new row
(CreateOnceMixin, apps/core/api/base.py). That works only if every new row gets an id of its own: a UUID
of version 7, which carries the time it was made. Any other UUID is refused, before it can be taken for a
repeat of another row. And an id a row of another shop already holds is found only when the insert is
refused (id_taken), as the guard hides that row from every look before it: the route then answers that the
id is taken, and nothing more (03 §5.4).
"""

import uuid

import psycopg
from django.db import IntegrityError, models
from rest_framework import serializers


def uuid7_only(value: uuid.UUID) -> None:
    """A serializer validator for a client-made id: refuses any UUID that is not of version 7."""
    # A random UUID (version 4) would still be unique, but scatters the table's index (ADR-0007). The nil
    # UUID, all zeros, is what a careless client sends for every new row, and each one would come back as
    # the first one's repeat, never made.
    if value.version != 7:
        raise serializers.ValidationError("Ids are UUIDv7, made on the device (ADR-0007).", code="id.not_uuid7")


def id_taken(error: IntegrityError, model: type[models.Model]) -> bool:
    """True when the refused insert broke `model`'s primary key: its id was already taken. Used by every route that
    makes a row with the client's id: CreateOnceMixin's creates, and the workers' gives (PPL-7) and photos (PPL-9,
    StaffViewSet)."""
    # PostgreSQL names the broken rule, and it names a table's primary key "<table>_pkey".
    cause = error.__cause__
    return (
        isinstance(cause, psycopg.errors.UniqueViolation)
        and cause.diag.constraint_name == f"{model._meta.db_table}_pkey"
    )
