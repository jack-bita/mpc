---
status: accepted
date: 2026-10-18
source: "03-architecture.md §2 — AD17"
standing: decided
cost-to-change: high
---

# ADR-0031 · The web address is fixed before the first device is registered

## Context

Each device's offline data, service worker and device key belong to the web address (the browser's origin).

## Decision

The product name and domain are chosen before the first real device is paired (OWN-3, before OPS-5), and never change after go-live.

## Consequences

- **Good:** No forced re-registration of every device.
- **Cost:** The product name must be settled early.

## Alternatives considered

- **A temporary address, moved later** — every device would have to send its outbox, register again and lose its offline PIN checks.

## Enforced by

- OWN-3 must be answered before OPS-5.
- The go-live checklist (04 §16).

## Related

- [ADR-0019](0019-offline-data-lives-in-indexeddb-through-dexie.md) · Offline data lives in IndexedDB, through Dexie
- [ADR-0018](0018-two-kinds-of-identity-devices-and-people.md) · Two kinds of identity: devices and people
- Docs: 03 §2

## Notes

- Cost to change: high after go-live; nothing before it.
