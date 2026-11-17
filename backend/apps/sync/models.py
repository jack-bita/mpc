"""apps/sync/models.py — the answer log: the answer the push gave each document a laptop sent, kept so that the
same document sent again gets the same answer (SYNC-4; 03 §5.5, §6.3).

    shop  document  laptop          #   answer    change no.  flags   reason                  carried from
    MPC   0193…a7   Laptop ya Dawa  12  accepted  43          —       —                       —
    MPC   0193…b2   Laptop ya Dawa  13  invalid   —           1 flag  document.type_unknown   —
    MPC   0193…c9   Laptop Vyakula  41  accepted  57          —       —                       Dawa #14, by Neema

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


# The type checker's Django plugin writes each base its own get_next_by_created_at() and get_previous_by_created_at(),
# then calls each pair of copies a clash: each is one and the same method, from ShopScoped, as Django builds the table
# (`created_at` once). The plugin's mistake, not ours, so ignored here, on this line only; every field below keeps its
# own type.
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
    # Carried: a record another laptop of the shop made, which a rescue file brought to the laptop that sent it
    # (SYNC-12, 03 §6.7). The laptop that made it and its number there, so its time is checked against that laptop's
    # record before it, not the sending laptop's (ATT-1's sign 1); and who loaded the file, as rule 7 wants every
    # change to name its person. All three or none. An invalid line keeps them too, when they passed their checks: its
    # time is still that laptop's clock, which the time checks around it must know (SYNC-12's second review). No
    # index on who loaded it: nothing reads lines by it, and nobody is ever deleted (rule 7), so PROTECT never
    # searches it.
    carried_from = models.ForeignKey(
        "people.Device", on_delete=models.PROTECT, related_name="+", null=True, blank=True, db_index=False
    )
    carried_seq = models.PositiveBigIntegerField(null=True, blank=True)
    loaded_by = models.ForeignKey(
        "people.StaffMember", on_delete=models.PROTECT, related_name="+", null=True, blank=True, db_index=False
    )

    class Meta(AppendOnly.Meta, CounterRecord.Meta):
        # Both bases' Meta, so the guard stays the default manager (CORE-1, ADR-0042). No error codes on these rules:
        # only the push writes this table, so a broken rule is a bug in our code, a server error and a log line.
        indexes = [
            # A laptop's lines by its number, leading with `shop`: the record before a clock-in, the laptop's highest
            # number, a gap's lines (apps/sync/push.py) each read a few rows of one laptop, not the whole log (ATT-1).
            models.Index(fields=["shop", "device", "device_seq"], name="sync_pusheddocument_device_seq"),
            # The lines carried from a laptop, by their number there, for the record before one of that laptop's
            # (apps/sync/push.py, _record_before). Only the carried lines, which are few: a rescue is a last resort.
            models.Index(
                fields=["shop", "carried_from", "carried_seq"],
                name="sync_pusheddocument_carried",
                condition=models.Q(carried_from__isnull=False),
            ),
        ]
        constraints = [
            # One line per document in a shop: two copies of one sale sent at the same moment can't both be written,
            # so the second is refused here and finds the first one's answer. Also the index the push looks a document
            # up by, leading with `shop`.
            models.UniqueConstraint(fields=["shop", "document_id"], name="sync_pusheddocument_one_per_document"),
            models.CheckConstraint(
                condition=models.Q(status__in=PushedStatus.values), name="sync_pusheddocument_status_known"
            ),
            # An accepted document has nothing it was refused for: no reason, and no wrong fields either.
            models.CheckConstraint(
                condition=~models.Q(status=PushedStatus.ACCEPTED) | models.Q(reason="", reason_fields={}),
                name="sync_pusheddocument_accepted_has_no_reason",
            ),
            # An invalid one says why, and only that. It took no change number, as it saved nothing: a laptop would
            # wait for one forever. And it names no flag: none of its rules was checked, and the one flag it raises,
            # about this line, is found by its subject.
            models.CheckConstraint(
                condition=~models.Q(status=PushedStatus.INVALID)
                | (models.Q(posted_seq__isnull=True, flags=[]) & ~models.Q(reason="")),
                name="sync_pusheddocument_invalid_has_only_a_reason",
            ),
            # A laptop numbers its documents from 1. Not one line per laptop number: a laptop wiped and started again
            # from 1 would have every new sale refused. SYNC-5, which owns the numbers and their gaps, decides that.
            models.CheckConstraint(
                condition=models.Q(device_seq__gte=1), name="sync_pusheddocument_device_seq_from_one"
            ),
            # A carried line names where it was made, its number there and who loaded it, all three, or none.
            models.CheckConstraint(
                condition=models.Q(carried_from__isnull=True, carried_seq__isnull=True, loaded_by__isnull=True)
                | models.Q(carried_from__isnull=False, carried_seq__gte=1, loaded_by__isnull=False),
                name="sync_pusheddocument_carried_whole",
            ),
            # Carried from another laptop, never from the one that sent it: that one sends its own records as its own.
            models.CheckConstraint(
                condition=~models.Q(carried_from=models.F("device")), name="sync_pusheddocument_carried_from_another"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.type} {self.document_id}: {self.status}"
