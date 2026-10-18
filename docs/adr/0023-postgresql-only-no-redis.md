---
status: accepted
date: 2026-10-18
source: "03-architecture.md §2 — AD9"
standing: default
cost-to-change: low
revisit: "if job volume or latency outgrows the database queue, or R2 needs live updates"
---

# ADR-0023 · PostgreSQL is the only data store in R1; no Redis

## Context

One small server (2 GB). Background jobs — exports, nightly checks, cleanups — are light.

## Decision

Background jobs use Django's tasks framework with the django-tasks-db backend (a `db_worker` container); supercronic runs scheduled management commands; sessions live in PostgreSQL. No Redis, no Celery.

## Consequences

- **Good:** One service fewer to run, monitor and back up.
- **Good:** A job enqueued inside a posting transaction is stored in that transaction, so it never runs for a rolled-back document.
- **Cost:** Jobs are polled from the database; very high volume would need Redis or Celery.

## Alternatives considered

- **Celery + Redis** — the common Django choice, but a second service on a 2 GB server, and a job can run before the transaction that created it commits.
- **Cron only** — no queued, retried jobs for exports.

## Enforced by

- OPS-7: the worker and scheduler run; jobs are safe to run twice and ping a heartbeat.

## Related

- [ADR-0027](0027-one-linux-server-with-docker-compose.md) · The real shop runs on one Linux server, with Docker Compose
- Docs: 03 §5.11
