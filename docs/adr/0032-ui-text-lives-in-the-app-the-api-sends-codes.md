---
status: accepted
date: 2026-10-18
source: "03-architecture.md §2 — AD18"
standing: decided
cost-to-change: low
---

# ADR-0032 · UI text lives in the app; the API sends codes

## Context

Swahili first, with an English switch (spec principle 1). The counter works offline, so the translations must live on the device.

## Decision

next-intl with `sw.json` and `en.json` in the app. API errors carry a code and parameters — `{"code": "sale.below_floor", "params": {…}}` — that the app translates. The server sends no sentences for the UI.

## Consequences

- **Good:** One place for translations; it works offline; a new language needs no backend change.
- **Cost:** Every error code needs a message in each language.

## Alternatives considered

- **Server-side translation (Django i18n)** — needs the network, and splits translations between two places.
- **English only** — the shop works in Swahili.

## Enforced by

- UI-1: switching to English changes every visible string.
- CORE-6: `test_error_shape`.
- UI-2: an API error shows its Swahili message; 04 §3.2 Done #7.

## Related

- [ADR-0025](0025-the-api-contract-is-generated.md) · The API contract is generated
- Docs: 03 §5.10, §7.4 · 02 §21
