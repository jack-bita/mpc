---
status: accepted
date: 2026-11-06
source: "UI-1, chosen by Jack while building UI-1; supersedes ADR-0032 (03 §2 — AD18, §7.4)"
standing: confirmed
cost-to-change: low
---

# ADR-0040 · UI text lives in the app, through use-intl; the API sends codes

> Supersedes [ADR-0032](0032-ui-text-lives-in-the-app-the-api-sends-codes.md). What changed: the screens get their
> words through use-intl, next-intl's own core, not through next-intl itself. Everything else stands.

## Context

Swahili first, with an English switch (spec principle 1). The counter works offline, so the translations must live on
the device. ADR-0032 chose next-intl. When UI-1 came to add it (6 Nov 2026, version 4.14.9), next-intl had grown tools
that pull words out of the code. They bring a code compiler (`@swc/core`, tens of MB with its own program) and a file
watcher (`@parcel/watcher`), and both want install scripts, which our pnpm settings refuse unless allowed one by one.
The app is a static build with no language in its web address (03 §7.4), so it uses none of next-intl's own parts:
its server side, its routing and its middleware.

## Decision

- use-intl, next-intl's core, by the same author, gives the screens their words: the provider, `useTranslations()` and
  ICU messages with parts to fill in ("Toleo {version}"). The words live in `frontend/messages/sw.json` and `en.json`.
- Swahili is open unless someone switches. This browser keeps the choice until UI-9 keeps it on the person.
- API errors carry a code and parameters — `{"code": "sale.below_floor", "params": {…}}` — that the app translates. The
  server sends no sentences for the UI.

## Consequences

- **Good:** One place for translations; it works offline; a new language needs no backend change.
- **Good:** About 100 KB of packages instead of a compiler and a file watcher, and nothing runs when they install.
- **Cost:** Every error code needs a message in each language.
- **Cost:** If the app ever puts the language in its web address or renders on a server, next-intl's own parts are
  worth adding then. Its screens use the same `useTranslations()`, so no screen would change.

## Alternatives considered

- **next-intl** — what ADR-0032 chose. Its own parts are for a server and for routing, which this app doesn't have,
  and its 4.x versions bring the compiler and the watcher.
- **Server-side translation (Django i18n)** — needs the network, and splits translations between two places.
- **English only** — the shop works in Swahili.

## Enforced by

- UI-1: `language.test.tsx` (every page in English has no Swahili left), `messages.test.ts` (both books hold the same
  keys and the same parts to fill in), and `text-rule.test.ts` (a lint rule refuses a word typed into a screen).
- CORE-6: `test_error_shape`.
- UI-2: an API error shows its Swahili message; 04 §3.2 Done #7.

## Related

- [ADR-0032](0032-ui-text-lives-in-the-app-the-api-sends-codes.md) · UI text lives in the app; the API sends codes
  (superseded by this one)
- [ADR-0025](0025-the-api-contract-is-generated.md) · The API contract is generated
- [ADR-0039](0039-the-apps-look-is-one-layer-over-shadcn.md) · The app's look is one layer over shadcn
- Docs: 03 §2 AD18, §5.10, §7.4 · 02 §21
