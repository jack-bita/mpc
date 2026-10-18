---
status: accepted
date: 2026-10-18
source: "03-architecture.md §2 — AD8"
standing: default
cost-to-change: medium
revisit: "before a second real shop goes live (R3): switch on row-level security"
---

# ADR-0022 · Tenancy is enforced in one place; row-level security comes later

## Context

The product is multi-shop from day one, and shops must never see each other's data. MPC is the only real shop until R3.

## Decision

A request-scoped current shop (a context variable) set by authentication; scoped model managers that fail closed, raising when no shop is set; one base API view; "same shop" checks on every write; and sweep tests that find every model and route by themselves. Cross-shop reads use an explicit, searchable `system_context()`. PostgreSQL row-level security (RLS) is added before a second real shop.

## Consequences

- **Good:** One place to get right; a forgotten filter raises instead of leaking.
- **Cost:** No second wall (RLS) yet.
- **Cost:** Every query needs a shop context; system jobs must say so explicitly.

## Alternatives considered

- **RLS from day one** — foreign-key checks bypass it, so it doesn't stop cross-shop links; it complicates migrations and connections; its benefit arrives with the second shop.
- **A database or schema per shop** — strong isolation, but every migration runs once per shop; overkill for small shops.

## Enforced by

- CORE-2: `test_query_without_shop_raises`.
- CORE-7: `test_every_model_has_shop`, `test_no_route_leaks_across_shops`.
- SYNC-4: `test_uuid_from_other_shop_rejected_silently`.

## Related

- [ADR-0014](0014-practice-mode-is-a-separate-practice-shop.md) · Practice mode is a separate practice shop
- [ADR-0029](0029-demo-is-separate-with-fake-data-only.md) · The demo is a separate deployment with fake data only
- Docs: 03 §5.4
