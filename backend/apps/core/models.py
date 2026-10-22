"""apps/core/models.py — the abstract base models every table builds on.

UUIDModel gives a table its `id` (UUIDv7, ADR-0007); TimeStamped gives it `created_at`. Both are abstract:
they make no table of their own, they only pass their columns on to the models that inherit them.
PPL-1's User and CORE-2's ShopScoped build on them, and every shop's table builds on ShopScoped.
"""

import uuid

from django.db import models


class UUIDModel(models.Model):
    # ADR-0007: ids are time-ordered UUIDv7, so each new row goes at the end of the primary-key index,
    # not at a random place in it, and devices can make ids offline with no server to ask.
    # Python makes the id, not the database: the server knows a sale's id before it saves the sale,
    # so it can link the lines to it. A device sends its own id instead, and Django keeps that one.
    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)

    class Meta:
        # No table for UUIDModel itself: the card's check that makemigrations finds nothing to do.
        abstract = True


class TimeStamped(models.Model):
    # When the server saved the row, in UTC (settings: USE_TZ). auto_now_add: Django fills it in on the
    # first save and ignores any value passed in, so no one can set a false time. A device's own clock
    # is not trusted: counter records keep it apart, in `client_time` (03 §5.3).
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True
