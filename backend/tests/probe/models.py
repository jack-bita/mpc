"""tests/probe/models.py — test-only tables built on core's base models.

Note is the smallest table a shop could have: a line of text, plus what ShopScoped gives every shop's
table (`id`, `shop`, `created_at`, `created_by` and the guard on reads). The tenancy tests
(apps/core/tests/test_shop_scoped.py) fill it with two shops' rows and check that each read sees only
the rows it may.
"""

from django.db import models

from apps.core.models import ShopScoped


class Note(ShopScoped):
    text = models.CharField(max_length=100)

    def __str__(self) -> str:
        return self.text
