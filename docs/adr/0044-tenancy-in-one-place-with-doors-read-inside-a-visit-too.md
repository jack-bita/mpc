---
status: accepted
date: 2026-11-18
source: "PPL-10's review, in the plan Jack approved on 18 Nov 2026; supersedes ADR-0042 (03 §2 — AD8, §5.4)"
standing: decided
cost-to-change: medium
revisit: "before a second real shop goes live (R3): switch on row-level security, and settle who may change a person who works at two shops (AUTH-7)"
---

# ADR-0044 · Tenancy is enforced in one place, with named doors for a login and a person's change, read inside a shop's visit too; row-level security comes later

> Supersedes [ADR-0042](0042-tenancy-in-one-place-with-doors-for-a-login-and-a-persons-change.md). What changed: the
> person's door may be read inside a shop's visit, when that visit changes the person, not only before any shop is
> open.

## Context

ADR-0042 lets the person's door (`shops_of_person`) serve a change to a person, whose name, language, font or
switch-off every shop where they work shows on their staff row: the save finds those shops through the door, then
writes a line in each, one block after another (SYNC-15). It said the door is read before any shop is open, which was
true of both callers then: the person's own settings route and the admin read no shop's rows. PPL-10 adds a third: on
the workers' page, Meneja fixes Asha's full name inside his visit to shop A, where shop A is already open, and the new
name must still reach every shop where Asha works.

## Decision

Everything ADR-0042 decided stays: a request-scoped current shop, managers that fail closed, "same shop" checks on
every write, sweep tests, only three named ways past the guard (`system_context()` for system jobs, `all_shops` for the
superuser's admin pages, and the doors), and row-level security before a second real shop. What changes is when the
person's door may be read:

- A **door** reads the shops' ids that a login, or a change to a person that must reach each of their shops, needs, and
  nothing else: before any shop is open, for a login, the person's own settings and the admin; or inside the visit of
  the shop where the change is made, for a fix on the workers' page (`change_worker`, PPL-10).
- Read inside a visit, the door still returns every shop where the person works, the visit's own among them, ordered by
  id. The change then opens each in turn, one block after another, never one inside another, and reads each job
  through the guard inside its own shop, as before. The visit's shop is closed for none of this: each block opens its
  shop over it and hands it back as it ends (`shop_context`).

## Consequences

- **Good:** One door still answers "where does this person work?" for every caller, and a fix made at one shop reaches
  every laptop that shows the person.
- **Good:** Nothing new past the guard: still shops' ids alone, from the one listed file, with its test.
- **Cost:** Code inside shop A's visit writes a line in shop B's change log. It is the person's staff row, which shop B
  shows anyway, and nothing of shop B is read but the person's own job there; but who may make that change is asked of
  shop A's job alone, and shop B's audit trail holds no line of it. Both must be settled before a person holds current
  jobs at two real shops (AUTH-7's row).
- **Cost:** No second wall (RLS) yet, as ADR-0042 said.

## Alternatives considered

- **Leave the visit's shop first, then read the door** — the save and its audit line must share one transaction with
  the visit's own checks; closing the shop mid-visit would leave the guard open to whatever the code reads next.
- **Record the change only in the visit's shop** — the person's other shops' laptops would show the old name until they
  paired again, as ADR-0042 already found.
- **A line on PPL-10's card instead of an ADR** — the written decision said "before any shop is open"; a changed
  decision ships as a new ADR (CLAUDE.md, docs rules).

## Enforced by

- Everything ADR-0042 names: CORE-2's `test_query_without_shop_raises`; CORE-7's sweep tests; AUTH-2's and AUTH-3's door
  tests (`test_key_door_reads_only_a_shop_id`, `test_person_door_reads_only_a_shop_id`); SYNC-15's
  `test_own_settings_recorded_in_every_shop`; SYNC-4's `test_uuid_from_other_shop_rejected_silently`.
- PPL-10: `test_a_full_name_fix_reaches_every_shop_where_they_work`, which fixes a name inside shop A's visit and finds
  the line in both shops.

## Related

- [ADR-0042](0042-tenancy-in-one-place-with-doors-for-a-login-and-a-persons-change.md) · Tenancy is enforced in one
  place, with named doors for a login and a person's change; row-level security comes later (superseded)
- [ADR-0036](0036-office-edits-are-recorded-by-our-own-trigger.md) · Office edits are recorded by our own trigger, into
  one table
- [ADR-0018](0018-two-kinds-of-identity-devices-and-people.md) · Two kinds of identity: devices and people
- Docs: 03 §5.4; 04 PPL-10, AUTH-7
