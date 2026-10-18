---
status: accepted
date: 2026-10-18
source: "03-architecture.md §2 — AD12"
standing: decided
cost-to-change: low
---

# ADR-0026 · Search runs on the device

## Context

Search is the strongest part of the sale screen (spec principle 4). It must work offline and find products by name, brand, animal and use ("dawa ya kupe").

## Decision

A small in-browser index (MiniSearch) over names, other names, tags and synonyms, brand and shelf label, with Swahili-friendly normalising; this side's products and this device's frequent items rank higher. The server keeps its own search (`pg_trgm` + `unaccent`) for office screens and R3.

## Consequences

- **Good:** Instant results, offline.
- **Cost:** Two search implementations; the device index rebuilds after each pull.

## Alternatives considered

- **Server search only** — fails offline, and adds a round trip to every keystroke.
- **PostgreSQL full-text search** — PostgreSQL has no Swahili stemmer.

## Enforced by

- CAT-7: 5,000 products answer in under 50 ms.
- CAT-3: server search for office screens.

## Related

- [ADR-0019](0019-offline-data-lives-in-indexeddb-through-dexie.md) · Offline data lives in IndexedDB, through Dexie
- Docs: 03 §5.14
