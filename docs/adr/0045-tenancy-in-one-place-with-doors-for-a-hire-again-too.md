---
status: accepted
date: 2026-11-18
source: "PPL-11, in the plan Jack approved on 18 Nov 2026; supersedes ADR-0044 (03 §2 — AD8, §5.4)"
standing: decided
cost-to-change: medium
revisit: "before a second real shop goes live (R3): switch on row-level security, and settle who may change, or hire, a person who works at two shops (AUTH-7)"
---

# ADR-0045 · Tenancy is enforced in one place, with named doors for a login, a person's change and a hire again; row-level security comes later

> Supersedes [ADR-0044](0044-tenancy-in-one-place-with-doors-read-inside-a-visit-too.md). What changed: the person's
> door may also be read inside a shop's visit to refuse hiring a person again while they work at another shop.

## Context

ADR-0044 lets the person's door (`shops_of_person`) serve a login, and a change to a person that every shop where they
work must hear of, inside the visit of the shop where it is made. PPL-11 adds a third kind of caller: on the workers'
page, Meneja hires Baraka again, who left shop A. If Baraka works at shop B by now, a new job at shop A would make him
a person at two shops: AUTH-3 would refuse his login, and shop A could fix the name and phone that shop B shows
(ADR-0044's cost). Until AUTH-7 settles that, the hire is refused, and only the door can tell shop A's visit that a job
elsewhere exists.

## Decision

Everything ADR-0044 decided stays: a request-scoped current shop, managers that fail closed, "same shop" checks on
every write, sweep tests, only three named ways past the guard (`system_context()` for system jobs, `all_shops` for the
superuser's admin pages, and the doors), and row-level security before a second real shop. What changes is what the
person's door may serve:

- A **door** reads the shops' ids that a login, a change to a person that must reach each of their shops, or a hire
  again needs, and nothing else: before any shop is open, for a login, the person's own settings and the admin; or
  inside the visit of the shop where the act is made, for a fix on the workers' page (`change_worker`, PPL-10), a
  hire again (`hire_again`, PPL-11), and the check of a phone typed on *Ongeza* (`add_worker`, PPL-11), which asks
  whether a hire again would take the person, and so reads the door only for a person whose every job at this shop
  ended.
- For a hire again, and for that phone, the door's answer is only counted: a shop other than the visit's among the ids
  refuses the hire (`staff.works_elsewhere`), or leaves the phone only in use (`unique`). Nothing of that shop is read
  or opened, and neither answer names a shop.

## Consequences

- **Good:** One door still answers "where does this person work?" for every caller, and a hire again can't make a
  person at two shops before AUTH-7.
- **Good:** Nothing new past the guard: still shops' ids alone, from the one listed file, with its test.
- **Cost:** The manager at shop A learns that Baraka, who worked there, now works at some other shop of the system:
  from a hire again's refusal, or, less directly, from his phone answering only "in use" on *Ongeza* where it would
  name him if he worked nowhere. Either way the same one fact: it names no shop and nothing of it, and Baraka's own job
  at shop A ended, so shop A knew him.
- **Cost:** No second wall (RLS) yet, as ADR-0044 said.

## Alternatives considered

- **Let the hire go through** — Baraka could no longer log in at shop B (AUTH-3 refuses a person at two shops), and
  shop A could change what shop B shows of him, with no line in shop B's audit trail.
- **Look for the job at shop B through `system_context()`** — opens every shop's rows to request code, which rule 1
  forbids; the door reads ids alone.
- **A line on PPL-11's card instead of an ADR** — the written decision names what the door serves; a changed decision
  ships as a new ADR (CLAUDE.md, docs rules).

## Enforced by

- Everything ADR-0044 names: CORE-2's `test_query_without_shop_raises`; CORE-7's sweep tests; AUTH-2's and AUTH-3's door
  tests (`test_key_door_reads_only_a_shop_id`, `test_person_door_reads_only_a_shop_id`); SYNC-15's
  `test_own_settings_recorded_in_every_shop`; SYNC-4's `test_uuid_from_other_shop_rejected_silently`; PPL-10's
  `test_a_full_name_fix_reaches_every_shop_where_they_work`.
- PPL-11: `test_a_person_working_at_another_shop_is_not_hired_again`, which hires again inside shop A's visit a person
  with a current job at shop B; `test_the_phone_of_anyone_else_is_only_in_use[left here, works elsewhere]`, which types
  that person's phone on *Ongeza* there.

## Related

- [ADR-0044](0044-tenancy-in-one-place-with-doors-read-inside-a-visit-too.md) · Tenancy is enforced in one place, with
  named doors for a login and a person's change, read inside a shop's visit too; row-level security comes later
  (superseded)
- [ADR-0018](0018-two-kinds-of-identity-devices-and-people.md) · Two kinds of identity: devices and people
- Docs: 02 §5; 03 §5.4; 04 PPL-11, AUTH-7
