---
status: accepted
date: 2026-10-17
source: "02-domain-model.md §2 — D2"
standing: decided
cost-to-change: high
---

# ADR-0002 · Stock is kept per stock location

## Context

Stock sits on shelves and in store rooms, and rarely moves between sides (spec §3). R1 needs one stock figure per side, but store-room counts (Later) and transfers between sides (R2) need stock per place.

## Decision

Every stock movement and balance belongs to a `StockLocation`. In R1 each side has exactly one default location, created automatically by `create_shop` and hidden in the UI.

## Consequences

- **Good:** Transfers and store-room counts arrive later with no ledger migration.
- **Good:** The balance key (location × product × batch) is stable from day one.
- **Cost:** One more column and join in stock queries; the UI must hide a concept R1 users never see.

## Alternatives considered

- **Stock per side, no locations** — simplest now, but adding store rooms or transfers later would mean migrating every movement.

## Enforced by

- SHOP-2: one hidden default location per side.
- STK-1: `StockMovement` and `StockBalance` keyed by location × product × batch.

## Related

- [ADR-0001](0001-a-side-is-a-section-of-one-shop.md) · A side is a section of one shop
- [ADR-0021](0021-posting-services-and-append-only-ledgers.md) · Posting services write the ledgers; the database refuses edits
- Docs: 02 §4, §7
