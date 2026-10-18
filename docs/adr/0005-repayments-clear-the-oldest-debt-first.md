---
status: accepted
date: 2026-10-17
source: "02-domain-model.md §2 — D5"
standing: confirmed
cost-to-change: high
---

# ADR-0005 · Repayments clear the oldest debt first

## Context

Debts are repaid in parts or in full, and arguments about what is still owed are common (spec §3). The owner needs to know who owes what, and since when.

## Decision

A repayment clears the oldest open debt first, starting on the side where the customer pays, then the other sides; staff can pick specific debts instead. Each match is stored as an `Allocation`. The server allocates again at posting (oldest first) unless staff picked debts; a leftover stays as customer credit and clears the next debt automatically.

## Consequences

- **Good:** Exact aging and "which goods are still unpaid" — the end of arguments.
- **Good:** An auditable trail of every match.
- **Cost:** Allocation must lock the contact's open debts, so two repayments can't clear the same debt (03 §5.5).

## Alternatives considered

- **Newest debt first** — old debts stay open forever.
- **Spread across all debts** — hard to explain at the counter.
- **One running balance with no matching** — no aging, and no answer to "which goods are unpaid?"

## Enforced by

- DEBT-6: `test_e5_debt_clears_oldest_first`; E5 is a shared test vector.
- DEBT-2: a Hypothesis test — an allocation never exceeds what is open (B1).

## Related

- [ADR-0004](0004-credit-is-the-unpaid-part-of-a-confirmed-sale.md) · Credit is the unpaid part of a confirmed sale
- [ADR-0020](0020-sync-push-documents-pull-changes.md) · Sync = push documents, pull changes
- Docs: 02 §8 Allocation, E5 · 03 §6.3

## Notes

- Updated 18 Oct 2026 by 03 Appendix B (02 v1.1): the server re-runs the allocation at posting.
