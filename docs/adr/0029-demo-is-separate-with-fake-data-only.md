---
status: accepted
date: 2026-10-18
source: "03-architecture.md §2 — AD15"
standing: decided
cost-to-change: low
---

# ADR-0029 · The demo is a separate deployment with fake data only

## Context

The project is a public portfolio. Recruiters must be able to click around with no risk to real data, and the demo should cost nothing.

## Decision

The same code is deployed a second time on Render's free plan, with its own database, filled by a seed script with fake data and reset nightly. Every merge to `main` deploys there first. Production releases are rehearsed on a scratch copy on the production server itself.

## Consequences

- **Good:** A recruiter can never reach real data, even if a tenancy bug ships.
- **Good:** It costs nothing.
- **Cost:** The free plan sleeps after 15 minutes, and its database must be re-created every 30 days.
- **Cost:** The demo is not a staging copy of production.

## Alternatives considered

- **A demo shop on the production server** — one tenancy bug away from showing real data to strangers.
- **A paid always-on demo now** — about TZS 16,000 a month; worth it once recruiters open the link (03 §18).

## Enforced by

- OPS-2: every merge to `main` deploys the demo.
- DATA-1: `test_seed_demo_refuses_live_shop`.
- OPS-3: `test_one_tap_demo_refused_with_live_shop`.

## Related

- [ADR-0028](0028-real-shop-data-stays-in-tanzania.md) · Real shop data stays in Tanzania, on a Lineserve server in Dar es Salaam
- [ADR-0022](0022-tenancy-in-one-place-rls-later.md) · Tenancy is enforced in one place; row-level security comes later
- [ADR-0014](0014-practice-mode-is-a-separate-practice-shop.md) · Practice mode is a separate practice shop
- Docs: 03 §12, §13 · 04 BP15
