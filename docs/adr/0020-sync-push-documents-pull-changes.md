---
status: accepted
date: 2026-10-18
source: "03-architecture.md §2 — AD6"
standing: decided
cost-to-change: high
---

# ADR-0020 · Sync = push documents, pull changes

## Context

Devices can be offline for hours during power cuts. Facts made offline already happened. Reference data (products, prices, staff) is edited online only.

## Decision

**Push:** outbox documents in device order, safe to resend (idempotent by UUID), each posted in its own transaction and answered `accepted`, `duplicate`, `invalid` or `retry`. **Pull:** reference-data changes after a cursor, from a per-shop change log whose numbers follow commit order. Offline facts are accepted, then flagged.

## Consequences

- **Good:** No merge logic: facts are append-only, and reference data has one writer.
- **Good:** A device can never skip a change that committed late.
- **Cost:** Numbering locks the shop's counter row for the last moment of each transaction.
- **Cost:** Rules broken offline become flags someone must review.

## Alternatives considered

- **Two-way sync with conflict resolution (last-write-wins, CRDTs)** — needed only when one record is edited in two places; here it would silently lose money records.
- **A hosted sync service** — less code, but the posting rules would live outside our code, and data might leave Tanzania (AD14).

## Enforced by

- SYNC-1: `test_change_numbers_follow_commit_order`.
- SYNC-4: `test_posts_in_device_seq_order`, `test_server_error_answers_retry`.
- SYNC-11: `e2e/clock-in-offline.spec.ts` — exactly one event on the server.

## Related

- [ADR-0008](0008-documents-in-ledgers-out.md) · Documents in, ledgers out
- [ADR-0019](0019-offline-data-lives-in-indexeddb-through-dexie.md) · Offline data lives in IndexedDB, through Dexie
- [ADR-0021](0021-posting-services-and-append-only-ledgers.md) · Posting services write the ledgers; the database refuses edits
- Docs: 03 §6.3, §6.4
