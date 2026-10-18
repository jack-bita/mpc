---
status: accepted
date: 2026-10-18
source: "03-architecture.md §2 — AD4"
standing: decided
cost-to-change: high
---

# ADR-0018 · Two kinds of identity: devices and people

## Context

PINs must only work on shop devices (D12); offline work needs a trusted device; a stolen device must be stoppable at once.

## Decision

A registered shop device holds a device key — an HttpOnly cookie, stored hashed on the server — and the sync talks to the device. A person is identified by PIN on a shop device, or by password on their own phone for office screens. Devices are paired with a short code confirmed by a manager; blocking a device kills its key at once. Every document names the person and the device.

## Consequences

- **Good:** A blocked device stops on its next request.
- **Good:** Every record says who did it, and where.
- **Cost:** Pairing is an extra setup step (the demo skips it — 04 BP15).
- **Cost:** A 4-digit offline PIN check on a stolen device can be guessed by someone skilled; the answer is blocking the device (an accepted limit, 03 §5.9).

## Alternatives considered

- **People only, no device identity** — PINs would work from any browser in the world.
- **One shared login per device** — records would carry no names (spec principle 6).

## Enforced by

- AUTH-1: `test_pairing_code_expires`, `test_device_key_stored_hashed`.
- AUTH-2: `test_blocked_device_refused`.
- AUTH-4 and SYNC-10: PIN sessions online and offline, with lockouts that double.

## Related

- [ADR-0012](0012-one-person-is-one-user.md) · One person is one user
- [ADR-0017](0017-one-address-session-cookies-allauth.md) · One web address, session cookies, and django-allauth for passwords
- Docs: 03 §5.9
