---
status: superseded
date: 2026-11-02
source: "AUTH-2, confirmed with Jack in chat at AUTH-2's review; supersedes ADR-0022 (03 §2 — AD8, §5.4)"
standing: confirmed
cost-to-change: medium
revisit: "before a second real shop goes live (R3): switch on row-level security"
superseded-by: ADR-0042
---

# ADR-0037 · Tenancy is enforced in one place, with named doors; row-level security comes later

> Superseded by [ADR-0042](0042-tenancy-in-one-place-with-doors-for-a-login-and-a-persons-change.md) on 2026-11-10
> (SYNC-15): a door may serve a change to a person as well as a login, and the person's door reads every shop where
> they work, in id order.

> Supersedes [ADR-0022](0022-tenancy-in-one-place-rls-later.md). What changed: besides `system_context()`, two other
> reads may pass the shop guard, each named and listed: the admin's `all_shops`, and the login doors.

## Context

The product is multi-shop from day one, and shops must never see each other's data. ADR-0022 said every read that
crosses shops goes through `system_context()`, for system jobs. Two other reads have needed to since. The superuser's
admin pages list every shop's rows through `all_shops` (CORE-2). And a login must find which shop a request works for
before any shop is open: a device's key names no shop, so AUTH-2's login reads the shop of the device that holds the
key. `system_context()` would open every shop for that one read, inside request code, where it is never allowed.

## Decision

A request-scoped current shop (a context variable) set by authentication; scoped model managers that fail closed,
raising when no shop is set; one base API view for office routes and one for device routes; "same shop" checks on every
write; and sweep tests that find every model and route by themselves. Only three ways pass the guard, each named so a
search finds every use, and each kept to its place by the sweep:

- `system_context()` opens every shop, for system jobs and commands only, never in request code.
- `all_shops`, a second manager on each shop table, is the superuser's admin pages' only.
- A **login door** reads, before any shop is open, the one shop's id a login needs, and nothing else. Every door lives
  in `apps/people/login_doors.py`, which is on the sweep's `HAND_BUILT_QUERIES` with its reason, and a test pins what
  each door reads. Everything after the door is read through the guard, inside that shop. Today one door, for a
  device's key (`shop_of_device_key`, AUTH-2).

PostgreSQL row-level security (RLS) is added before a second real shop.

## Consequences

- **Good:** One place to get right; a forgotten filter raises instead of leaking.
- **Good:** A login reads one shop's id past the guard, never a row, and a new door can't arrive unseen: it is a new
  function in one listed file, with its own test.
- **Cost:** No second wall (RLS) yet.
- **Cost:** Every query needs a shop context; system jobs must say so explicitly.
- **Cost:** The sweep's lists name whole files, so a second door in `login_doors.py` passes the scan by its file; only
  review and its own test keep it to a shop's id.

## Alternatives considered

- **RLS from day one** — foreign-key checks bypass it, so it doesn't stop cross-shop links; it complicates migrations
  and connections; its benefit arrives with the second shop.
- **A database or schema per shop** — strong isolation, but every migration runs once per shop; overkill for small
  shops.
- **`system_context()` for the login** — it opens every shop for the whole block, in request code, where the sweep
  rightly refuses it.
- **The pairing request as the device's door** (key → request → device) — it held a second copy of the key's hash, and
  a path past the guard that no scan could see; AUTH-2 moved the hash to the device instead (02 v1.12).

## Enforced by

- CORE-2: `test_query_without_shop_raises`.
- CORE-7: `test_every_model_has_shop`, `test_no_route_leaks_across_shops`, `test_system_context_only_in_system_code`,
  `test_all_shops_only_in_admin`, `test_hand_built_queries_only_where_listed`.
- AUTH-2: `test_key_door_reads_only_a_shop_id`, `test_no_device_route_leaks_across_shops`.
- SYNC-4: `test_uuid_from_other_shop_rejected_silently`.

## Related

- [ADR-0022](0022-tenancy-in-one-place-rls-later.md) · Tenancy is enforced in one place; row-level security comes later
  (superseded)
- [ADR-0018](0018-two-kinds-of-identity-devices-and-people.md) · Two kinds of identity: devices and people
- [ADR-0014](0014-practice-mode-is-a-separate-practice-shop.md) · Practice mode is a separate practice shop
- [ADR-0029](0029-demo-is-separate-with-fake-data-only.md) · The demo is a separate deployment with fake data only
- Docs: 03 §5.4
