---
paths:
  - "backend/apps/sync/**"
  - "backend/apps/*/documents.py"
  - "frontend/src/offline/**"
---

# The offline engine (ADR-0019, ADR-0020)

<!-- Source: 03 §5.5, §6. The hardest part of the system: change it slowly and test it hard. -->

- One document = one action = one server transaction. Idempotent by UUID: the same document twice returns the stored answer.
- Push posts in `device_seq` order and answers `accepted`, `duplicate`, `invalid` or `retry`. A broken business rule never stops a batch — accept, then raise a Flag. A server error answers `retry` and stops the batch there.
- A UUID that already exists in another shop → `invalid`, revealing nothing about the other record.
- Pull returns the changes after a cursor, in commit order (numbers taken last, from the shop's locked `ShopSequence` row). The device applies a page in one Dexie transaction, then moves its cursor.
- On the device, `saveDocument()` writes the document, the next `device_seq`, the outbox row and the pending effects in **one** Dexie transaction. Pending effects drop when the cursor passes the document's `posted_seq`.
- One sync at a time across tabs (Web Locks). An update never interrupts a busy counter screen, and the outbox is sent before an update.
- Documents carry `schema_version`; the server accepts the current and the previous one.
- A new document type needs all four: a server handler with its permission, a schema version, the device side, and tests on both sides.
- Nothing secret syncs: no buying prices, PIN hashes or passwords — tests prove it.
- A Dexie schema change is a new database version with an upgrade; never edit an old version.
