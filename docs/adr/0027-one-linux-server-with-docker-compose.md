---
status: accepted
date: 2026-10-18
source: "03-architecture.md §2 — AD13"
standing: decided
cost-to-change: medium
---

# ADR-0027 · The real shop runs on one Linux server, with Docker Compose

## Context

One shop, a small budget, and one developer who wants skills that transfer to any job.

## Decision

One rented VPS runs Caddy, Django (gunicorn), a task worker, a scheduler and PostgreSQL with Docker Compose. One monthly bill covers it all: PostgreSQL runs inside the server. Nothing ties us to a provider.

## Consequences

- **Good:** The cheapest setup that is still professional; it moves to any provider unchanged.
- **Good:** It builds Docker and Linux skills.
- **Cost:** We run backups, updates and monitoring ourselves (stage 3).
- **Cost:** One server is one point of failure — answered by tested backups and device replay.

## Alternatives considered

- **A platform service (PaaS) for production** — easier operations, but more expensive at this size, and the data would leave Tanzania (AD14).
- **A managed database** — a second bill.

## Enforced by

- OPS-4: SSH keys only, firewall, automatic security updates.
- OPS-5: `compose.prod.yml`, Caddy and HTTPS; no container runs as root.
- OPS-8 and OPS-10: backups and monitoring.

## Related

- [ADR-0028](0028-real-shop-data-stays-in-tanzania.md) · Real shop data stays in Tanzania, on a Lineserve server in Dar es Salaam
- [ADR-0023](0023-postgresql-only-no-redis.md) · PostgreSQL is the only data store in R1; no Redis
- [ADR-0015](0015-a-modular-monolith.md) · A modular monolith
- Docs: 03 §13

## Notes

- Cost to change: low to change provider; medium to change the approach.
