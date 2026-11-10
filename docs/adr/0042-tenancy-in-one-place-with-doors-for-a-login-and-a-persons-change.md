---
status: accepted
date: 2026-11-10
source: "SYNC-15, in the plan Jack approved on 10 Nov 2026; supersedes ADR-0037 (03 §2 — AD8, §5.4)"
standing: decided
cost-to-change: medium
revisit: "before a second real shop goes live (R3): switch on row-level security"
---

# ADR-0042 · Tenancy is enforced in one place, with named doors for a login and a person's change; row-level security comes later

> Supersedes [ADR-0037](0037-tenancy-in-one-place-with-named-doors.md). What changed: a door may serve a change to a
> person as well as a login, and the person's door reads every shop where they work, in id order, not two at most.

## Context

A person belongs to no shop; their job at each shop does. Their own language and font, their name, and whether they may
log in at all live on the person, yet every shop's laptops show them on that person's staff row (SYNC-2). So a change to
one of them must write a line in the change log of every shop where the person works, in one transaction (SYNC-15).
The save runs with no shop open: the person's own settings route reads no shop's rows, and neither does the admin. It
must first find those shops, which is the very read AUTH-3's login door already makes (`shops_of_person`), but
ADR-0037 kept a door for "the one shop's id a login needs".

## Decision

Everything ADR-0037 decided stays: a request-scoped current shop, managers that fail closed, "same shop" checks on
every write, sweep tests, and only three named ways past the guard (`system_context()` for system jobs, `all_shops` for
the superuser's admin pages, and the doors), with row-level security before a second real shop. What changes is what a
door may serve:

- A **door** reads, before any shop is open, the shops' ids that a login, or a change to a person that must reach each
  of their shops, needs, and nothing else. Every door lives in `apps/people/login_doors.py`, on the sweep's
  `HAND_BUILT_QUERIES` with its reason, and a test pins what each door reads. Everything after the door is read through
  the guard, inside each shop in turn.
- Two doors today: a device's key (`shop_of_device_key`, AUTH-2), and a person (`shops_of_person`, AUTH-3). The person's
  door reads the ids of every shop where they have a current job, ordered by id. The login only counts them (none, one,
  more than one); a change to the person opens one block per shop, one after another, in that order, so two such saves
  never deadlock (SYNC-15).

## Consequences

- **Good:** One door answers one question, "where does this person work?", for the login and for a change to them
  alike, so the two can't disagree about which jobs count.
- **Good:** Still a shop's id and nothing else past the guard, from one listed file, each door with its own test.
- **Cost:** The login's door no longer stops at two; a person has a handful of jobs at most, so it reads a few ids more.
- **Cost:** No second wall (RLS) yet, and the sweep's lists still name whole files, as ADR-0037 said.

## Alternatives considered

- **A second door for a person's change** — the same query twice, which could drift apart, and one more function past
  the guard that only review can keep to a shop's id.
- **`system_context()` for the save** — it opens every shop, in request code, where it is never allowed.
- **Record the change only in the visit's shop** — the person's other shops' laptops would keep the old language until
  they paired again; and the admin, where the name and the switch-off change, has no visit's shop at all.

## Enforced by

- CORE-2: `test_query_without_shop_raises`.
- CORE-7: `test_every_model_has_shop`, `test_no_route_leaks_across_shops`, `test_system_context_only_in_system_code`,
  `test_all_shops_only_in_admin`, `test_hand_built_queries_only_where_listed`.
- AUTH-2: `test_key_door_reads_only_a_shop_id`, `test_no_device_route_leaks_across_shops`.
- AUTH-3, SYNC-15: `test_person_door_reads_only_a_shop_id`, which pins that the person's door reads shops' ids alone,
  every one, in id order.
- SYNC-15: `test_own_settings_recorded_in_every_shop`.
- SYNC-4: `test_uuid_from_other_shop_rejected_silently`.

## Related

- [ADR-0037](0037-tenancy-in-one-place-with-named-doors.md) · Tenancy is enforced in one place, with named doors;
  row-level security comes later (superseded)
- [ADR-0018](0018-two-kinds-of-identity-devices-and-people.md) · Two kinds of identity: devices and people
- [ADR-0020](0020-sync-push-documents-pull-changes.md) · Sync = push documents, pull changes
- Docs: 03 §5.4, §6.4
