---
status: accepted
date: 2026-11-03
source: "AUTH-3, chosen by Jack while planning AUTH-3; supersedes ADR-0017 (03 §2 — AD3, §5.9)"
standing: confirmed
cost-to-change: medium
---

# ADR-0038 · One web address, session cookies, and django-allauth for passwords; a lost password is reset face to face

> Supersedes [ADR-0017](0017-one-address-session-cookies-allauth.md). What changed: a password user needs no email.
> The owner sets a first or forgotten password face to face, and the person chooses their own at the next login; an
> email link is only for people who have an email.

## Context

Shared shop devices use PINs; the owner and managers use passwords on their own phones. Logging out, suspending a
worker or blocking a device must take effect at once, and no secret should be readable by a script in the page.
ADR-0017 reset a lost password by an email link, so every password user needed an email. But most of the shop's people
have a phone and no email (Jack, PPL-1), and an SMS code costs money for each message and needs an account with an SMS
company.

## Decision

- The app files and the API come from one address (`https://<app-domain>/` and `/api/`). Logins use Django's session
  cookie (HttpOnly, Secure) with CSRF protection; no tokens are kept in JavaScript.
- django-allauth (headless, browser client) handles password login by phone or email, logout, rate limits and, later,
  two-factor codes and passkeys. Sign-up is closed: the owner adds people.
- **A first or forgotten password is set face to face.** The owner types a temporary password for the person and tells
  it to them; at the next login the person must choose their own (AUTH-6). The owner's own is reset by the superuser.
- Anyone who has an email may also reset their password by an email link, through allauth.
- No SMS for now. An SMS code can be added later, beside these.
- PIN login and device registration are our own small code, starting the same kind of session.

## Consequences

- **Good:** No CORS, nothing for a bad script to steal, and revocation is immediate.
- **Good:** A mature library handles the security-critical password login.
- **Good:** Nobody needs an email, and getting back in costs nothing.
- **Cost:** A person who forgets their password and has no email waits until they can see the owner.
- **Cost:** For a moment the owner knows the temporary password; it works only until the person chooses their own.
- **Cost:** Local development must mirror the single address (Caddy on `localhost:8080`).

## Alternatives considered

- **Resets by email only** (ADR-0017) — most of the shop's people have no email.
- **An SMS code** — costs money for each message and needs an SMS company's account; it can still be added later.
- **The person's phone paired as a shop device, then a PIN** — a paired device keeps an offline copy of the shop's data
  (prices, costs, debts), which a personal phone, lost or lent to the family, shouldn't hold.
- **Tokens (JWT) kept in JavaScript storage** — readable by any injected script, and hard to revoke before they expire.
- **A separate API domain** — needs CORS and third-party cookies, which browsers increasingly block.
- **Hand-written password login and resets** — the riskiest code to get wrong.

## Enforced by

- REPO-4: the app and `/api/` share one address locally.
- AUTH-2: `test_device_requests_need_csrf`.
- AUTH-3: `test_login_by_phone`, `test_signup_closed`, `test_login_rate_limited`, `test_password_reset_by_email`.
- AUTH-6: the temporary password, and the change it forces at the next login.

## Related

- [ADR-0017](0017-one-address-session-cookies-allauth.md) · One web address, session cookies, and django-allauth for
  passwords *(superseded by this one)*
- [ADR-0018](0018-two-kinds-of-identity-devices-and-people.md) · Two kinds of identity: devices and people
- [ADR-0012](0012-one-person-is-one-user.md) · One person is one user
- Docs: 02 §5, 03 §2 (AD3), §5.9, §5.10
