"""apps/sync/models.py — the receipt book: the answer the push gave each document a laptop sent, kept so that the
same document sent again gets the same answer (SYNC-4; 03 §5.5, §6.3).

    shop  document  laptop          #   answer    change no.  flags   reason
    MPC   0193…a7   Laptop ya Dawa  12  accepted  43          —       —
    MPC   0193…b2   Laptop ya Dawa  13  invalid   —           1 flag  document.type_unknown

Written only by the push, in the same transaction as the document it answers, so a saved document always has its line
and a repeat always finds it. A ledger: never changed, never deleted (ADR-0021).
"""

from django.db import models

from apps.core.models import AppendOnly, CounterRecord


class PushedStatus(models.TextChoices):
    # The two answers kept (03 §6.3). `duplicate` is never kept: it is one of these, given again. Nor `retry`: that
    # document's transaction rolled back, and the laptop sends it again later.
    ACCEPTED = "accepted", "Accepted"
    INVALID = "invalid", "Invalid"


# The type checker's Django plugin writes each base its own get_next_by_created_at(), and then calls the two copies a
# clash: they are one and the same method, from ShopScoped, as Django builds the table (`created_at` once). The plugin's
# mistake, not ours, so ignored here, on this line only; every field below keeps its own type.
class PushedDocument(AppendOnly, CounterRecord):  # type: ignore[misc]
    # One line per document a laptop pushed. AppendOnly first, so its save() and delete() run first and refuse a
    # change; CounterRecord gives the laptop, its number and both clocks. created_by (ShopScoped): who made it at the
    # counter, empty when the document named nobody of this shop.

    # No index of its own: the one-line-per-document rule below is one, and leads with `shop` (as core.Change does).
    shop = models.ForeignKey("shops.Shop", on_delete=models.PROTECT, related_name="+", db_index=False)
    # The document's own id, made on the laptop (ADR-0007): the sale's id, not this line's, which has its own (`id`).
    # So another shop's laptop that sends the same id gets a line in its own shop, telling it nothing of the first.
    document_id = models.UUIDField()
    # The type and version as the laptop named them, an unknown one too, so the flag can say what came.
    type = models.CharField(max_length=40)
    schema_version = models.PositiveIntegerField()
    status = models.CharField(max_length=10, choices=PushedStatus)
    # Accepted: the last change number its save took (posted_seq, 03 §6.4); empty when it changed nothing a laptop
    # keeps. Always empty for an invalid one, which saved nothing.
    posted_seq = models.PositiveBigIntegerField(null=True, blank=True)
    # The flags the answer named, as [{"id": "…", "kind": "negative_stock"}]: a flag's id and kind never change.
    flags = models.JSONField(default=list, blank=True)
    # Invalid: why, as the API's error shape says it: the code, and each wrong field of the payload with its codes.
    reason = models.CharField(max_length=100, blank=True)
    reason_fields = models.JSONField(default=dict, blank=True)

    class Meta(AppendOnly.Meta, CounterRecord.Meta):
        # Both bases' Meta, so the guard stays the default manager (CORE-1, ADR-0022). No error codes on these rules:
        # only the push writes this table, so a broken rule is a bug in our code, a server error and a log line.
        constraints = [
            # One line per document in a shop: two copies of one sale sent at the same moment can't both be written,
            # so the second is refused here and finds the first one's answer. Also the index the push looks a document
            # up by, leading with `shop`.
            models.UniqueConstraint(fields=["shop", "document_id"], name="sync_pusheddocument_one_per_document"),
            models.CheckConstraint(
                condition=models.Q(status__in=PushedStatus.values), name="sync_pusheddocument_status_known"
            ),
            # An accepted document has nothing it was refused for.
            models.CheckConstraint(
                condition=~models.Q(status=PushedStatus.ACCEPTED) | models.Q(reason=""),
                name="sync_pusheddocument_accepted_has_no_reason",
            ),
            # An invalid one says why, and took no change number, as it saved nothing: a laptop would wait for one
            # forever.
            models.CheckConstraint(
                condition=~models.Q(status=PushedStatus.INVALID)
                | (models.Q(posted_seq__isnull=True) & ~models.Q(reason="")),
                name="sync_pusheddocument_invalid_has_reason_no_number",
            ),
            # A laptop numbers its documents from 1. Not one line per laptop number: a laptop wiped and started again
            # from 1 would have every new sale refused. SYNC-5, which owns the numbers and their gaps, decides that.
            models.CheckConstraint(
                condition=models.Q(device_seq__gte=1), name="sync_pusheddocument_device_seq_from_one"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.type} {self.document_id}: {self.status}"
