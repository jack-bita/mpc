---
status: accepted
date: 2026-10-18
source: "03-architecture.md §2 — AD2"
standing: decided
cost-to-change: medium
---

# ADR-0016 · The shop app is a static PWA built with Next.js

## Context

The counter must open and work with no internet (spec principle 9). Anything rendered on a server can't.

## Decision

Next.js builds the app into plain files (`output: 'export'`). Every screen renders in the browser; a Serwist service worker keeps all app files on the device; there is no Node server in production — no server components at runtime, no server actions, no middleware.

## Consequences

- **Good:** The app opens offline.
- **Good:** Plain files are cheap and fast to serve from Caddy.
- **Cost:** Not how Next.js is usually used: record pages use a query string, and images aren't optimised.
- **Cost:** Server-rendered public pages (R3) would be a separate addition.

## Alternatives considered

- **Next.js with a Node server (the usual setup)** — pages rendered on a server can't open offline.
- **A plain React app built with Vite** — also static and a fine choice; Next.js was kept for the stack chosen in the spec, its file-based routes, and an easy path to server-rendered public pages in R3.

## Enforced by

- REPO-3: `pnpm build` writes plain files to `out/` that open with no Node server.
- SPIKE-1: the app installs and opens offline on the shop's real devices.
- SYNC-11: a CI budget keeps the counter code under 300 KB compressed.

## Related

- [ADR-0019](0019-offline-data-lives-in-indexeddb-through-dexie.md) · Offline data lives in IndexedDB, through Dexie
- [ADR-0017](0017-one-address-session-cookies-allauth.md) · One web address, session cookies, and django-allauth for passwords
- Docs: 03 §7, §7.7
