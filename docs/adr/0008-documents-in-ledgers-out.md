---
status: accepted
date: 2026-10-17
source: "02-domain-model.md §2 — D8"
standing: decided
cost-to-change: high
---

# ADR-0008 · Documents in, ledgers out

## Context

Many devices, often offline, record what happened. The owner's numbers — stock, money, balances and attendance — must stay exact and auditable, and resending must be safe.

## Decision

People make documents: a sale, a delivery, a count, a clock-in. A document is everything that happened in one action. Devices send documents; only the server writes ledger rows (stock, money, balances, attendance), one document per database transaction. Ledger rows are never rewritten; fixes are new rows that point at what they fix.

## Consequences

- **Good:** Business rules live in one place: the posting services.
- **Good:** Resending is safe, and history is complete.
- **Cost:** More tables (documents and ledgers).
- **Cost:** Devices show *pending effects* until the server confirms a document.

## Alternatives considered

- **Devices update balances directly** — two devices offline would overwrite each other's changes.
- **Editable records plus an audit log** — the log becomes the real truth, and records can still be changed.

## Enforced by

- SYNC-4: one document = one transaction — `test_same_batch_twice_posts_once`.
- SALE-2: `post_sale()` writes every ledger row of a sale in one transaction.
- CORE-3: the database refuses edits to ledger rows (ADR-0021).

## Related

- [ADR-0020](0020-sync-push-documents-pull-changes.md) · Sync = push documents, pull changes
- [ADR-0021](0021-posting-services-and-append-only-ledgers.md) · Posting services write the ledgers; the database refuses edits
- [ADR-0007](0007-ids-and-numbers-are-made-on-the-device.md) · IDs and numbers are made on the device
- Docs: 02 §1 · 03 §5.5

## Notes

- Updated 18 Oct 2026 by 03 Appendix B (02 v1.1): a document is everything that happened in one action.
