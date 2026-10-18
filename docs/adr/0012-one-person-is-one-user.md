---
status: accepted
date: 2026-10-17
source: "02-domain-model.md §2 — D12"
standing: decided
cost-to-change: high
---

# ADR-0012 · One person is one user

## Context

Staff change often and some have no smartphone; the same person may work at MPC and in the demo or practice shop; a PIN must be useless off the shop's devices (spec §3, §6). Django can't swap its user model after the first migration.

## Decision

A custom `User` — no username; optional phone, email and password — is one human across shops. `StaffMember` is that person's job at one shop and holds the PIN. PIN login works only on registered shop devices. The custom `User` is the very first migration: nothing runs `migrate` before it (04 BP5).

## Consequences

- **Good:** One identity, many shops; suspending a staff member doesn't touch the person.
- **Good:** PIN-only staff need no password or email.
- **Cost:** Password users (owner, managers) need an email for resets (allauth).
- **Cost:** Getting the first migration wrong is very expensive — hence the guard.

## Alternatives considered

- **Django's default user with a username** — can't be swapped later, and usernames mean nothing to shop staff.
- **One user per shop membership** — the same person twice, with two logins.

## Enforced by

- PPL-1: `test_phone_stored_as_plus255`, `test_user_without_password`, `test_superuser_needs_email`.
- PPL-2: `test_one_user_staff_in_two_shops`.
- AUTH-4: `test_pin_login_only_on_active_device`.
- The Claude Code guard (`.claude/hooks/guard.py`) refuses `migrate` until PPL-1's migration exists.

## Related

- [ADR-0018](0018-two-kinds-of-identity-devices-and-people.md) · Two kinds of identity: devices and people
- [ADR-0017](0017-one-address-session-cookies-allauth.md) · One web address, session cookies, and django-allauth for passwords
- Docs: 02 §5 · 03 §5.9 · 04 BP5
