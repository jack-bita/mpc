---
status: accepted
date: 2026-10-18
source: "03-architecture.md §2 — AD5"
standing: decided
cost-to-change: medium
---

# ADR-0019 · Offline data lives in IndexedDB, through Dexie

## Context

The counter needs products, prices, stock, customers and staff on the device, and must save documents that survive restarts.

## Decision

Reference data is copied into IndexedDB through Dexie 4, one database per shop. Documents are saved locally and queued in an outbox in the same local transaction.

## Consequences

- **Good:** Large, lasting storage; typed tables, testable with fake-indexeddb, and live queries for React.
- **Cost:** Browsers can evict storage, so the app asks for persistent storage and is installed (SPIKE-1, SYNC-12).
- **Cost:** Schema changes need Dexie versions with upgrades.

## Alternatives considered

- **localStorage** — a few megabytes of strings, read and written synchronously.
- **Raw IndexedDB** — the same storage, with verbose callbacks and no typed tables or live queries.
- **SQLite compiled to WebAssembly** — a real SQL engine, but a larger download and less proven on the shop's mid-range phones.

## Enforced by

- SYNC-6: `db.stores.test.ts` — two shops in one browser get two databases.
- SYNC-8: `outbox.save.test.ts` — the document and its outbox row in one transaction.
- SYNC-12: persistent storage and the unsent-records warning.

## Related

- [ADR-0020](0020-sync-push-documents-pull-changes.md) · Sync = push documents, pull changes
- [ADR-0016](0016-the-shop-app-is-a-static-pwa-built-with-next-js.md) · The shop app is a static PWA built with Next.js
- Docs: 03 §6.1, §6.2
