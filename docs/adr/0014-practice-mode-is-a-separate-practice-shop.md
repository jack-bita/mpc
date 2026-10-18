---
status: accepted
date: 2026-10-17
source: "02-domain-model.md §2 — D14"
standing: decided
cost-to-change: low
---

# ADR-0014 · Practice mode is a separate practice shop

## Context

New workers need to practise without touching real money, and staff change often (spec §7.1).

## Decision

Practice mode is a separate shop (`kind = practice`, `practice_of` → the live shop) with a copy of the products, and fake customers and money (R2; the public demo covers practice until then).

## Consequences

- **Good:** Shop isolation already guarantees practice never touches real records.
- **Good:** One device database per shop keeps practice data apart on shared devices.
- **Cost:** The product copy must be refreshed now and then.

## Alternatives considered

- **A practice flag on records** — every query must remember to filter it; one mistake mixes fake money into real reports.

## Enforced by

- SHOP-1: `kind` and `practice_of` — `test_shop_kind_must_be_known`.
- SYNC-6: one device database per shop.
- R2 PRAC epic.

## Related

- [ADR-0022](0022-tenancy-in-one-place-rls-later.md) · Tenancy is enforced in one place; row-level security comes later
- [ADR-0029](0029-demo-is-separate-with-fake-data-only.md) · The demo is a separate deployment with fake data only
- Docs: 02 §4 Shop · 03 §6.1
