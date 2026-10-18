---
status: accepted
date: 2026-10-17
source: "02-domain-model.md §2 — D3"
standing: confirmed
cost-to-change: high
---

# ADR-0003 · A sale belongs to one side; a bill groups sales

## Context

Each side keeps its own stock, money and debts (D1), yet one customer may take goods from both sides and pay once at either side (spec §3, §7.4).

## Decision

A `Sale` always belongs to exactly one side. When a customer buys on both sides and pays once, a `Bill` (R2) groups one sale per side and holds the shared receipt and EFD number. Each sale keeps its own side, number, stock and debt. Money one side received for the other is shown as an inter-side amount until a `side_transfer` settles it.

## Consequences

- **Good:** Drawers, stock and debts per side stay exact without splitting lines.
- **Good:** R1 (Drugs only) never needs the bill layer.
- **Cost:** Mixed purchases need the bill layer and an inter-side settlement step (R2).

## Alternatives considered

- **One sale with lines from both sides** — every drawer, stock and debt report would have to split lines by side.
- **Two unrelated sales** — the customer pays twice, or staff juggle notes between the sides.

## Enforced by

- SALE-2: `Sale` belongs to one side.
- R2 BILL epic: `test_e6_mixed_bill_foods_holds_15000_for_drugs` (02 E6).

## Related

- [ADR-0001](0001-a-side-is-a-section-of-one-shop.md) · A side is a section of one shop
- [ADR-0004](0004-credit-is-the-unpaid-part-of-a-confirmed-sale.md) · Credit is the unpaid part of a confirmed sale
- [ADR-0006](0006-anything-charged-to-a-customer-is-a-sale.md) · Anything charged to a customer is a sale
- Docs: 02 §9, E6
