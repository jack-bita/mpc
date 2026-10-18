---
status: accepted
date: 2026-10-18
source: "03-architecture.md §2 — AD3"
standing: confirmed
cost-to-change: medium
---

# ADR-0017 · One web address, session cookies, and django-allauth for passwords

## Context

Shared shop devices use PINs; the owner and managers use passwords on their own phones. Logging out, suspending a worker or blocking a device must take effect at once, and no secret should be readable by a script in the page.

## Decision

The app files and the API come from one address (`https://<app-domain>/` and `/api/`). Logins use Django's session cookie (HttpOnly, Secure) with CSRF protection; no tokens are kept in JavaScript. django-allauth (headless, browser client) handles password login by email or phone, password resets by email, rate limits and, later, two-factor codes and passkeys. PIN login and device registration are our own small code, starting the same kind of session.

## Consequences

- **Good:** No CORS, nothing for a bad script to steal, and revocation is immediate.
- **Good:** A mature library handles the security-critical password flows.
- **Cost:** Every password user needs an email (allauth can't reset by phone yet).
- **Cost:** Local development must mirror the single address (Caddy on `localhost:8080`).

## Alternatives considered

- **Tokens (JWT) kept in JavaScript storage** — readable by any injected script, and hard to revoke before they expire.
- **A separate API domain** — needs CORS and third-party cookies, which browsers increasingly block.
- **Hand-written password login and resets** — the riskiest code to get wrong.

## Enforced by

- REPO-4: the app and `/api/` share one address locally.
- AUTH-2: `test_device_requests_need_csrf`.
- AUTH-3: `test_login_by_phone`, `test_signup_closed`, `test_login_rate_limited`.

## Related

- [ADR-0018](0018-two-kinds-of-identity-devices-and-people.md) · Two kinds of identity: devices and people
- [ADR-0012](0012-one-person-is-one-user.md) · One person is one user
- Docs: 03 §5.9, §5.10
