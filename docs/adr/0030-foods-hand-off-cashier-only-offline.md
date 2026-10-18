---
status: accepted
date: 2026-10-18
source: "03-architecture.md §2 — AD16"
standing: confirmed
cost-to-change: low
---

# ADR-0030 · Foods hand-off: through the server with a network, cashier-only without

## Context

The Foods side runs writer → cashier → loader on different devices (R2). Power cuts switch off the router, and after a while mobile data and the devices too (confirmed).

## Decision

With a network, orders pass writer → server → cashier. With no network, the Foods side sells cashier-only on one screen and writers read orders out. Every device records its offline time from R1; at R2 those numbers decide whether a local hub is worth building.

## Consequences

- **Good:** Nothing extra to build, power or secure; the sync protocol stays the same.
- **Cost:** Slower on very busy days without a network.

## Alternatives considered

- **A battery router or UPS** — useless when mobile data also goes down — the shop's case.
- **A local hub** — a second server with HTTPS for a local address and its own sync; Later, if the outage numbers justify it.
- **QR hand-off** — the writer must walk the phone over to the cashier.

## Enforced by

- SYNC-14: devices record outages; the *Hali ya vifaa* page shows them.
- R2 FLOW epic: cashier-only selling when the network is down.

## Related

- [ADR-0020](0020-sync-push-documents-pull-changes.md) · Sync = push documents, pull changes
- Docs: 03 §6.10, §6.11

## Notes

- Cost to change: low to add a hub later — the sync protocol stays the same.
