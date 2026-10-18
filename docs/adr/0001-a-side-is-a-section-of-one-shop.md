---
status: accepted
date: 2026-10-17
source: "02-domain-model.md §2 — D1"
standing: confirmed
cost-to-change: high
---

# ADR-0001 · A side is a section of one shop

## Context

MPC has two sides under one roof — Drugs and Foods — each with its own workers and cash drawer. Some products sell on both sides at the same price, and a customer may take goods from both sides and pay once (spec §3). The spec left open whether a side is a branch or a section (spec §6).

## Decision

A side is a section of one shop. Sides share products, prices and contacts; each side has its own stock, drawer, staff roles and debts. A second site one day means more sides, grouped under a branch (Later).

## Consequences

- **Good:** One product list and one customer list; cross-side sales and combined debts stay simple.
- **Good:** Per-side numbers (stock, cash, debts, roles) are exact by design.
- **Cost:** Anything that differs per side must be modelled on purpose: `ProductSide`, roles per side, side settings.
- **Cost:** A different price per side isn't possible without a change (listed as Later in 02 §19).

## Alternatives considered

- **Each side a separate shop (tenant)** — two product and customer lists; combined debts and mixed bills would cross tenants, which the tenancy rules forbid.
- **A side as a branch** — branches are separate sites; MPC's sides share one roof, one product list and one set of customers.

## Enforced by

- SHOP-2: `create_shop` makes one stock location and one cash drawer per side — `test_create_shop_makes_location_and_drawer_per_side`.
- PPL-3: permissions are checked per side (X1) — `test_grant_limited_to_its_side`.
- CORE-4: a side setting beats a shop setting — `test_side_row_beats_shop_row`.

## Related

- [ADR-0002](0002-stock-is-kept-per-stock-location.md) · Stock is kept per stock location
- [ADR-0003](0003-a-sale-belongs-to-one-side-a-bill-groups-sales.md) · A sale belongs to one side; a bill groups sales
- [ADR-0033](0033-one-website-attendance-first.md) · One website with everything, built one part after another: attendance first
- Docs: spec §3, §6 · 02 §4
