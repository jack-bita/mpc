"""tests/probe/models.py — test-only tables built on core's base models.

Note is the smallest table a shop could have: a line of text, plus what ShopScoped gives every shop's
table (`id`, `shop`, `created_at`, `created_by` and the guard on reads). The tenancy tests
(apps/core/tests/test_shop_scoped.py) fill it with two shops' rows and check that each read sees only
the rows it may.

Entry and VoidableEntry are ledgers in miniature, for the append-only tests
(apps/core/tests/test_append_only.py, ADR-0021): Entry stands for a stock movement, never changed once
written; VoidableEntry stands for a payment, which may be voided once and is then frozen (03 §5.6).
"""

from django.db import models

from apps.core.models import ShopScoped


class Note(ShopScoped):
    text = models.CharField(max_length=100)

    def __str__(self) -> str:
        return self.text


class Entry(ShopScoped):
    # Money as a Decimal with 2 places, as a real ledger keeps it (ADR-0024).
    amount = models.DecimalField(max_digits=14, decimal_places=2)

    def __str__(self) -> str:
        return str(self.amount)


class VoidableEntry(ShopScoped):
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    # The void stamp (03 §5.6): empty while the row counts, filled once when it is voided. The fourth
    # part, `void_approval`, links to an Approval row; that table comes in R1, so the probe goes without.
    voided_at = models.DateTimeField(null=True, blank=True)
    # Who voided it. The same choices as ShopScoped's created_by: named, not imported (ADR-0035);
    # PROTECT, since nothing is deleted (rule 7); no index of its own, since indexes lead with `shop`.
    voided_by = models.ForeignKey(
        "people.StaffMember",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        db_index=False,
    )
    void_reason = models.TextField(blank=True)

    def __str__(self) -> str:
        return str(self.amount)
