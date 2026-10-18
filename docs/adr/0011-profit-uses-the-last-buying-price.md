---
status: accepted
date: 2026-10-17
source: "02-domain-model.md §2 — D11"
standing: default
cost-to-change: low
revisit: "if the owner needs batch-accurate margins on Foods products (R2 reports)"
---

# ADR-0011 · Profit uses the last buying price

## Context

Buying prices change often and some are unknown at launch. The owner wants honest profit numbers (spec principle 11: never guess numbers).

## Decision

A sale line's cost is the latest `ProductCost` — for drugs, the batch's own cost — copied by the server onto the line at posting. No cost means "unknown", shown as unknown in reports.

## Consequences

- **Good:** Simple and honest.
- **Good:** Switching method later only affects new lines, because copied values never change (T4).
- **Cost:** Profit on stock bought at older prices is approximate.

## Alternatives considered

- **Weighted average cost** — more accurate, more machinery; it can be switched on later for new lines.
- **FIFO cost layers** — the most accurate, and heavy for R1.

## Enforced by

- CAT-2: `ProductCost`, visible only with `cost.view`.
- SALE-2: the server fills `unit_cost`; devices never hold buying prices.
- SALE-8: the batch cost is used for drugs.

## Related

- [ADR-0008](0008-documents-in-ledgers-out.md) · Documents in, ledgers out
- Docs: 02 §6, §9 · 03 §5.5
