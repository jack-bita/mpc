---
status: accepted
date: 2026-10-17
source: "02-domain-model.md §2 — D7"
standing: decided
cost-to-change: high
---

# ADR-0007 · IDs and numbers are made on the device

## Context

The counter works offline (spec principle 9), so a device can't ask the server for the next ID or receipt number — yet a printed slip must stay valid after sync.

## Decision

Counter records get UUIDv7 IDs on the device, and human numbers like `D2-0457` (side, device code, per-device counter). Device codes are never reused, even when a device is registered again.

## Consequences

- **Good:** An offline document is complete the moment it is saved.
- **Good:** Sending it twice is safe (idempotent by UUID).
- **Good:** UUIDv7 is time-ordered, so database indexes stay fast.
- **Cost:** Receipt numbers are unique but not continuous across devices.
- **Cost:** A device that loses its storage gets a new device code.

## Alternatives considered

- **Numbers from the server** — impossible offline.
- **Random UUIDv4 IDs** — fine offline, but they scatter database indexes.

## Enforced by

- CORE-1: `test_ids_are_uuid_version_7`, `test_ids_sort_by_creation_time`.
- AUTH-1: `test_device_code_never_reused`.
- SALE-4: receipt numbers like `D2-0457`; SYNC-8: the next `device_seq` in the same local transaction.

## Related

- [ADR-0008](0008-documents-in-ledgers-out.md) · Documents in, ledgers out
- [ADR-0020](0020-sync-push-documents-pull-changes.md) · Sync = push documents, pull changes
- Docs: 02 §1 common fields · 03 §6.2
