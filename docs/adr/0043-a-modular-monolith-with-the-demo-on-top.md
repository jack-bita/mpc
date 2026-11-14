---
status: accepted
date: 2026-11-14
source: "OPS-3, in the plan Jack approved on 14 Nov 2026; supersedes ADR-0041 (03 §2 — AD1)"
standing: confirmed
cost-to-change: high
---

# ADR-0043 · A modular monolith, with control beside core and the demo on top

> Supersedes [ADR-0041](0041-a-modular-monolith-with-the-demo-seed-on-top.md). What changed: the `demo` app holds the one-tap demo's two routes beside the seed.

## Context

The system starts with one developer and one shop, has thirteen domain modules, and is meant to grow to other shops, so the code must stay easy to change as it grows. ADR-0041 split it into thirteen apps in seven layers, with a fourteenth, `demo`, alone on top, holding only the demo seed. OPS-3 adds the one-tap demo: *Jaribu demo* makes a visitor's browser a device of the demo shop and shows the sellers' PINs, which live in the seed's list of people (`PEOPLE`, `apps/demo/services.py`). A route in `people`, layer 2, can't read that list: no app imports `demo`.

## Decision

One Django project and one database, split into apps that follow the domain modules, in layers. An app imports only from lower layers: core, control → shops → people → catalog, contacts → inventory, money → sales, services, staffpay → sync, reports → demo. Apps on the same layer don't import each other, with three listed exceptions:

- `control` may import `core`. Because it sits on layer 0, every app may import `control`, and `control` imports nothing but `core`.
- `inventory` may import `money`, because deliveries pay suppliers.
- `services` may import `sales`, because a job's bill is a sale.

`demo` is not a domain module. It holds no tables, only what exists for the public demo: the demo seed, and the one-tap demo's two routes (`GET /api/devices/v1/demo/open/`, `POST /api/devices/v1/demo/`), which alone may read the seed's people and their PINs. On layer 7, alone, it may import every app, and no app imports it, so no other app's code calls either. `config/urls.py` mounts its routes, as it mounts every app's. What keeps both shut on the real server is not the layer but their own refusals: they work only where the sign `DEMO_SEED=yes` is set, which the real server never sets, and only on a database with no shop that isn't a demo.

import-linter checks this on every pull request. Business logic lives only in services and calculations.

## Consequences

- **Good:** There is no network between modules: one deploy and simple debugging.
- **Good:** Clean boundaries keep the door open to split a module out later.
- **Good:** Every app can write audit events and flags, and `control` stays free of domain code.
- **Good:** The demo's people and PINs live in one list: the seed sets the PINs from it, and the one-tap demo shows them from it, so the screen can't show a PIN the seed didn't set.
- **Good:** Everything that exists only for the demo sits in one app, with one pair of refusals.
- **Cost:** The boundaries hold only because CI checks them.
- **Cost:** `control` can't import any domain app, `shops` included. It points at rows by name (`"people.User"`) or by a type code plus a UUID (03 §5.1), and the caller passes in any value it needs, such as a setting.
- **Cost:** The seed and the one-tap routes ship inside the production image too, though the real server never runs them. Their sign (`DEMO_SEED=yes`, never set there) and their refusal of any shop that isn't a demo keep them shut there; the open check answers false there without a query.

## Alternatives considered

- **Microservices**: network failures, many deploys and distributed debugging, with no gain for one developer and one shop.
- **One big Django app**: no boundaries, so logic leaks everywhere and the code gets harder to change.
- **The one-tap routes in `people`, the PIN list moved down there** (OPS-3): no new ADR, but every real shop's server would carry the demo's PINs in its people code, and the list would leave the seed it belongs to.
- **The one-tap routes in `people`, with the PINs written a second time**: two lists, and a changed PIN on one would show a PIN that doesn't work.
- **The seed inside `people`** (DATA-1): `people` would hold code that wipes a database, and DATA-2 needs `staffpay`.
- **Keep `control` on layer 2** (ADR-0015): `shops` and `people` could not write audit events or flags, which CTRL-2 needs.

## Enforced by

- REPO-2: thirteen domain apps, each saying what it owns. DATA-1: `apps/demo`, which says it is not one.
- REPO-6: import-linter contracts in `backend/pyproject.toml`, run by `make check` and CI. `exhaustive = true`: an app with no layer turns the check red.
- DATA-1: `test_seed_demo_refuses_live_shop`. OPS-3: `test_one_tap_demo_refused_with_live_shop`, `test_one_tap_demo_refused_without_the_sign`.

## Related

- [ADR-0041](0041-a-modular-monolith-with-the-demo-seed-on-top.md) · A modular monolith, with control beside core and the demo seed on top (superseded by this ADR)
- [ADR-0029](0029-demo-is-separate-with-fake-data-only.md) · The demo is a separate deployment with fake data only
- [ADR-0021](0021-posting-services-and-append-only-ledgers.md) · Posting services write the ledgers; the database refuses edits
- Docs: 03 §2 (AD1), §4, §5.1, §5.10 · 04 BP15, OPS-3
