---
status: accepted
date: 2026-11-08
source: "DATA-1, in the plan Jack approved on 8 Nov 2026; supersedes ADR-0035 (03 §2 — AD1)"
standing: confirmed
cost-to-change: high
---

# ADR-0041 · A modular monolith, with control beside core and the demo seed on top

> Supersedes [ADR-0035](0035-a-modular-monolith-with-control-beside-core.md). What changed: a 14th app, `demo`, on a layer of its own above every other.

## Context

The system starts with one developer and one shop, has thirteen domain modules, and is meant to grow to other shops, so the code must stay easy to change as it grows. ADR-0035 split it into thirteen apps in seven layers. DATA-1 adds the demo seed, `manage.py seed_demo`, which builds the demo shop through the other apps' services. A management command lives in an installed app, and the image the demo runs holds `backend/apps` and `backend/config` only, so the seed can't be a loose script in `backend/scripts/`, as 03 §4's tree first had it. The seed starts with `shops` and `people`, but its next versions add clock-ins and a pay run (DATA-2, `staffpay`, layer 5), then products, sales, debts and drawer days (DATA-7, layers 3 to 5). On any domain layer it would soon import a layer above it.

## Decision

One Django project and one database, split into apps that follow the domain modules, in layers. An app imports only from lower layers: core, control → shops → people → catalog, contacts → inventory, money → sales, services, staffpay → sync, reports → demo. Apps on the same layer don't import each other, with three listed exceptions:

- `control` may import `core`. Because it sits on layer 0, every app may import `control`, and `control` imports nothing but `core`.
- `inventory` may import `money`, because deliveries pay suppliers.
- `services` may import `sales`, because a job's bill is a sale.

`demo` is not a domain module: it holds no tables, only the demo seed. On layer 7, alone, it may import every app, and no app imports it, so no other app's code calls the seed. What keeps the seed shut on the real server is not the layer but its own two refusals: it runs only where the sign `DEMO_SEED=yes` is set, which the real server never sets, and only on a database with no shop that isn't a demo.

import-linter checks this on every pull request. Business logic lives only in services and calculations.

## Consequences

- **Good:** There is no network between modules: one deploy and simple debugging.
- **Good:** Clean boundaries keep the door open to split a module out later.
- **Good:** Every app can write audit events and flags, and `control` stays free of domain code.
- **Good:** The seed grows with the domain apps without moving, and is in the image the demo and the browser tests run.
- **Cost:** The boundaries hold only because CI checks them.
- **Cost:** `control` can't import any domain app, `shops` included. It points at rows by name (`"people.User"`) or by a type code plus a UUID (03 §5.1), and the caller passes in any value it needs, such as a setting.
- **Cost:** The seed ships inside the production image too, though the real server never runs it. Its own sign (`DEMO_SEED=yes`, never set there) and its refusal of any shop that isn't a demo keep it shut there.

## Alternatives considered

- **Microservices**: network failures, many deploys and distributed debugging, with no gain for one developer and one shop.
- **One big Django app**: no boundaries, so logic leaks everywhere and the code gets harder to change.
- **The seed inside `people`, for now**: it fits DATA-1, but DATA-2 needs `staffpay`, so it would move again, and `people` would hold code that wipes a database.
- **A script in `backend/scripts/`**: the image holds only `backend/apps` and `backend/config`, so the demo couldn't run it, and import-linter, which reads `apps` only, wouldn't check it.
- **Keep `control` on layer 2** (ADR-0015): `shops` and `people` could not write audit events or flags, which CTRL-2 needs.

## Enforced by

- REPO-2: thirteen domain apps, each saying what it owns. DATA-1: `apps/demo`, which says it is not one.
- REPO-6: import-linter contracts in `backend/pyproject.toml`, run by `make check` and CI. `exhaustive = true`: an app with no layer turns the check red. A test commit where `core` imports `sales` goes red.

## Related

- [ADR-0035](0035-a-modular-monolith-with-control-beside-core.md) · A modular monolith, with control beside core (superseded by this ADR)
- [ADR-0029](0029-demo-is-separate-with-fake-data-only.md) · The demo is a separate deployment with fake data only
- [ADR-0021](0021-posting-services-and-append-only-ledgers.md) · Posting services write the ledgers; the database refuses edits
- Docs: 03 §2 (AD1), §4, §5.1, §5.2, §5.16
