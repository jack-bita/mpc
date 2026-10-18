---
status: accepted
date: 2026-10-17
source: "02-domain-model.md §2 — D4"
standing: decided
cost-to-change: high
---

# ADR-0004 · Credit is the unpaid part of a confirmed sale

## Context

Credit (*madeni*) is written in a book with a date, name, phone and items; arguments about amounts happen, and the open total is TZS 5–10 million (spec §3). Partners and suppliers also owe or are owed (R2).

## Decision

Credit is never a payment method. When a sale is confirmed, its unpaid part is posted as a `debt` entry in one balance ledger (`BalanceEntry`), held by a named contact with a phone. The same ledger serves customers, partners and suppliers, and holds only debts and what settles them — like the madeni book.

## Consequences

- **Good:** "Paid + credit = total" is a rule the system can check.
- **Good:** Every debt shows the date, contact, phone, items, amount, side and who gave it (B3).
- **Good:** One balance system for every kind of contact.
- **Cost:** No walk-in credit: a contact with a phone is always needed.

## Alternatives considered

- **Credit as a payment method** — mixes promises with money and breaks the drawer's expected cash.
- **A separate ledger per kind of contact** — the same logic written three times.

## Enforced by

- SALE-2: paid + credit = total; credit is never a payment (M4).
- DEBT-2: `BalanceEntry` is append-only; `ContactBalance` is updated in the same transaction.
- DEBT-5: credit needs a debt holder with a phone, `credit.give`, and an approval above the limit (B3).

## Related

- [ADR-0005](0005-repayments-clear-the-oldest-debt-first.md) · Repayments clear the oldest debt first
- [ADR-0006](0006-anything-charged-to-a-customer-is-a-sale.md) · Anything charged to a customer is a sale
- [ADR-0021](0021-posting-services-and-append-only-ledgers.md) · Posting services write the ledgers; the database refuses edits
- Docs: spec §8.2 · 02 §8
