---
status: accepted
date: 2026-10-18
source: "03-architecture.md §2 — AD14"
standing: confirmed
cost-to-change: medium
---

# ADR-0028 · Real shop data stays in Tanzania, on a Lineserve server in Dar es Salaam

## Context

Tanzania's Personal Data Protection Act (2022) requires a PDPC permit before personal data is transferred abroad. Customer names, phones and debts, and staff photos, are personal data.

## Decision

Production runs on a Lineserve VPS in Dar es Salaam — 2 GB for R1 (about TZS 38,000 a month), 4 GB from R2 — and its backups stay in Tanzania: Lineserve's backups plus a weekly encrypted copy on a USB drive at the shop. The public demo holds fake data only and can be hosted anywhere.

## Consequences

- **Good:** Compliant by default; local latency.
- **Cost:** Fewer providers to choose from; we test restores ourselves.

## Alternatives considered

- **A foreign provider (for example Hetzner in Europe)** — cheaper per GB, but personal data abroad needs a PDPC permit.
- **Another local provider** — six to ten times the price.

## Enforced by

- OPS-4: the production server in Dar es Salaam.
- OPS-8 and OPS-9: backups kept in Tanzania, restored and checked every week.
- OWN-5: the PDPC registration before the first go-live.

## Related

- [ADR-0027](0027-one-linux-server-with-docker-compose.md) · The real shop runs on one Linux server, with Docker Compose
- [ADR-0029](0029-demo-is-separate-with-fake-data-only.md) · The demo is a separate deployment with fake data only
- Docs: 03 §10, §13

## Notes

- Not legal advice: a local lawyer or the PDPC can confirm what applies to the shop.
