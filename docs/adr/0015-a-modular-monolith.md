---
status: accepted
date: 2026-10-18
source: "03-architecture.md §2 — AD1"
standing: decided
cost-to-change: high
---

# ADR-0015 · A modular monolith

## Context

One developer and one shop to start, thirteen domain modules, and a product meant to grow to other shops. The code must stay easy to change as it grows.

## Decision

One Django project and one database, split into apps that follow the domain modules, in layers: an app imports only from lower layers (core → shops → people, control → catalog, contacts → inventory, money → sales, services, staffpay → sync, reports), with two listed exceptions. import-linter checks this on every pull request. Business logic lives only in services and calculations.

## Consequences

- **Good:** No network between modules: one deploy, simple debugging.
- **Good:** Clean boundaries keep the door open to split a module out later.
- **Cost:** The boundaries hold only because CI checks them.

## Alternatives considered

- **Microservices** — network failures, many deploys and distributed debugging — no gain for one developer and one shop.
- **One big Django app** — no boundaries; logic leaks everywhere and the code gets harder to change.

## Enforced by

- REPO-2: thirteen apps, each saying what it owns.
- REPO-6: import-linter contracts — a test commit where `core` imports `sales` goes red.

## Related

- [ADR-0021](0021-posting-services-and-append-only-ledgers.md) · Posting services write the ledgers; the database refuses edits
- [ADR-0027](0027-one-linux-server-with-docker-compose.md) · The real shop runs on one Linux server, with Docker Compose
- Docs: 03 §5.1, §5.2
