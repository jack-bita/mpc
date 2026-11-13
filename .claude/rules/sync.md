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
- One sync at a time across tabs (Web Locks). An update never interrupts a busy counter screen (`useCounterBusy`, `src/offline/busy.ts`), and the outbox is sent before an update (`before-update.ts`, at most 10 s, then the switch goes ahead).
- A release that adds a list to the registry, or whose apps stop writing a record shape the server is to drop, raises `APP_NUMBER` (`src/lib/version.ts`) and `MIN_APP_VERSION` (`config/settings/base.py`) together; `test_app_number.py` keeps the minimum at or below the app's, and each number's lists in step with the registry and the app's drawers. The shape leaves the server's list only in a later release: a too-old app sends its outbox first, in the shapes it wrote. A new list also needs a database version whose upgrade removes the cursor, so the laptop bootstraps again (SYNC-13).
- The service worker pushes too, with the app closed (Background Sync, SYNC-16): it takes the same lock and wait, so code it loads (`push.ts`, `answer.ts`, `lock.ts`, `waiting.ts`, `api/make-client.ts`) never touches `window`, `document` or `localStorage` — `tsconfig.sw.json` checks it.
- Documents carry `schema_version`; the server accepts the current and the previous one (`test_document_types.py` checks the real list).
- A new document type needs all four: a server handler with its permission (or none, as a clock-in needs no key), a schema version, the device side, and tests on both sides. The server's half may come a card before the device's (ATT-1, then SYNC-11).
- Nothing secret syncs: no buying prices, PIN hashes or passwords — tests prove it. The device makes its own PIN checks (`pin_checks`, PBKDF2 with a salt of each check's own) and never sends them; each pull page and bootstrap drops, in its own transaction, the checks the staff rows no longer match (`dropOutdatedChecks`, SYNC-10).
- A Dexie schema change is a new database version with an upgrade; never edit an old version.
