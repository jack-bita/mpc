---
status: accepted
date: 2026-10-17
source: "02-domain-model.md §2 — D6"
standing: decided
cost-to-change: medium
---

# ADR-0006 · Anything charged to a customer is a sale

## Context

Besides goods, MPC charges for grinding and mixing per kg, and machine jobs mix services with MPC's own ingredients; jobs can be paid at any time (spec §3, §7.7).

## Decision

Goods, machine services and job charges all go through `Sale`. Services are products of kind `service`, priced per kg and never stocked; a job's bill is a sale.

## Consequences

- **Good:** One path for prices, bargaining, payments, credit, receipts and reports.
- **Cost:** Services and jobs (R2) must fit the sale's shape — deposits use `PaymentAllocation` before confirmation.

## Alternatives considered

- **A separate service order with its own payments and credit** — two of everything.

## Enforced by

- SALE-2: one posting path for every charge.
- R2 SVC epic: `services` may import `sales`, because a job's bill is a sale (03 §5.1).

## Related

- [ADR-0003](0003-a-sale-belongs-to-one-side-a-bill-groups-sales.md) · A sale belongs to one side; a bill groups sales
- [ADR-0004](0004-credit-is-the-unpaid-part-of-a-confirmed-sale.md) · Credit is the unpaid part of a confirmed sale
- Docs: 02 §11
