---
status: accepted
date: 2026-10-18
source: "03-architecture.md §2 — AD7"
standing: decided
cost-to-change: high
---

# ADR-0021 · Posting services write the ledgers; the database refuses edits

## Context

Rules T2 and T3: ledgers are never edited or deleted. Remembering is not enough — a bug, a migration or a hand-typed SQL query could still rewrite history.

## Decision

Each document type has one posting function that writes the document and all its ledger rows in one transaction. A migration helper adds a PostgreSQL trigger to each ledger table that refuses UPDATE and DELETE. Payments, money movements and attendance events allow exactly one change: filling the void stamp once. Dated-rule rows (prices, costs, settings, pay rates) are insert-only too.

## Consequences

- **Good:** History is protected by the database itself.
- **Good:** Fixes are visible: reversal rows and void stamps.
- **Cost:** Data repairs are new rows, never UPDATEs.
- **Cost:** The triggers need their own tests.

## Alternatives considered

- **Django code alone, no trigger** — a bug, a migration or a hand-typed query could still rewrite history.
- **Soft deletes on editable rows** — rows can still be changed; the audit log becomes the real ledger.

## Enforced by

- CORE-3: `test_append_only_update_fails_in_database`, `test_void_stamp_set_once`, `test_void_cannot_change_other_columns`.
- STK-9: nightly checks compare every cache with its ledger.

## Related

- [ADR-0008](0008-documents-in-ledgers-out.md) · Documents in, ledgers out
- [ADR-0015](0015-a-modular-monolith.md) · A modular monolith
- Docs: 02 T2, T3 · 03 §5.5, §5.6

## Notes

- Updated 18 Oct 2026 (03 v1.1, 04 Appendix A #3): attendance events also allow the one-time void stamp.
