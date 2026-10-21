---
status: accepted
date: 2026-10-21
source: "REPO-6, confirmed with Jack in chat; supersedes ADR-0015 (03 §2 — AD1)"
standing: confirmed
cost-to-change: high
---

# ADR-0035 · A modular monolith, with control beside core

> Supersedes [ADR-0015](0015-a-modular-monolith.md). What changed: `control` moves from layer 2 to layer 0, beside `core`.

## Context

The system starts with one developer and one shop, has thirteen domain modules, and is meant to grow to other shops, so the code must stay easy to change as it grows. ADR-0015 chose a modular monolith and put `control` on layer 2, beside `people`. But every app writes audit events and flags to `control`: 03 §5.16, and CTRL-2, where a `people` action writes an audit event when a staff member is suspended. On layer 2, `shops` (a lower layer) could not import `control`, and neither could `people` (the same layer, with no listed exception). REPO-6 found this while it turned the layers into import-linter contracts.

## Decision

One Django project and one database, split into apps that follow the domain modules, in layers. An app imports only from lower layers: core, control → shops → people → catalog, contacts → inventory, money → sales, services, staffpay → sync, reports. Apps on the same layer don't import each other, with three listed exceptions:

- `control` may import `core`. Because it sits on layer 0, every app may import `control`, and `control` imports nothing but `core`.
- `inventory` may import `money`, because deliveries pay suppliers.
- `services` may import `sales`, because a job's bill is a sale.

import-linter checks this on every pull request. Business logic lives only in services and calculations.

## Consequences

- **Good:** There is no network between modules: one deploy and simple debugging.
- **Good:** Clean boundaries keep the door open to split a module out later.
- **Good:** Every app can write audit events and flags, and `control` stays free of domain code.
- **Cost:** The boundaries hold only because CI checks them.
- **Cost:** `control` can't import any domain app, `shops` included. It points at rows by name (`"people.User"`) or by a type code plus a UUID (03 §5.1), and the caller passes in any value it needs, such as a setting.

## Alternatives considered

- **Microservices** — network failures, many deploys and distributed debugging, with no gain for one developer and one shop.
- **One big Django app** — no boundaries, so logic leaks everywhere and the code gets harder to change.
- **Keep `control` on layer 2** (ADR-0015) — `shops` and `people` could not write audit events or flags, which CTRL-2 needs.
- **Keep `control` on layer 2 and add a `people` → `control` exception** — `shops`, on layer 1, would still be cut off, and 03 says every app writes here.
- **Give `control` a new layer 1 and move every layer above it up by one** — the same rule, but every app's layer number would change, for no gain.

## Enforced by

- REPO-2: thirteen apps, each saying what it owns.
- REPO-6: import-linter contracts in `backend/pyproject.toml`, run by `make check` and CI. A test commit where `core` imports `sales` goes red.

## Related

- [ADR-0015](0015-a-modular-monolith.md) · A modular monolith (superseded by this ADR)
- [ADR-0021](0021-posting-services-and-append-only-ledgers.md) · Posting services write the ledgers; the database refuses edits
- [ADR-0027](0027-one-linux-server-with-docker-compose.md) · The real shop runs on one Linux server, with Docker Compose
- Docs: 03 §2 (AD1), §5.1, §5.2, §5.16
