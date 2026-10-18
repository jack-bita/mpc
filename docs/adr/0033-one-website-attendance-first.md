---
status: accepted
date: 2026-10-18
source: "04-build-plan.md §2 — BP7"
standing: confirmed
cost-to-change: medium
---

# ADR-0033 · One website with everything, built one part after another: attendance first

## Context

Jack confirmed one website and one repo for everything — attendance, the Drugs side and the Foods side (portion 4). The parts must still be built and adopted one at a time, and the first real use should test devices, PINs, offline storage and power cuts before money depends on them.

## Decision

One repo, one address. The parts are built in this order: attendance (R1b), then the Drugs side (R1), then the Foods side (R2). Each part is switched on in settings (`attendance.enabled`, each side's `is_live`); the shop starts using it once the owner agrees, at the review before its go-live *(default: as soon as it is ready)*.

## Consequences

- **Good:** The smallest real feature goes first; every worker on both sides uses it daily, and it fixes problem #2 (spec §4).
- **Good:** Devices, PINs, offline storage and power cuts are proven on real shop days before any money depends on them — while the Drugs product data is prepared.
- **Cost:** The Drugs side (problem #1) is ready a few weeks later than if it were built first.
- **Cost:** The product name, the web address and the PDPC registration are needed sooner.

## Alternatives considered

- **Drugs side first (the spec's earlier default)** — problem #1 sooner, but the first real use would carry money while devices and offline storage are unproven.
- **Separate systems or sites per part** — rejected by Jack: one website with everything.
- **Everything on one day** — too much training and risk at once; the build order stays even if the shop prefers this.

## Enforced by

- The stage order in 04 §1.
- SHOP-3: each side's `is_live` switch; ATT-2: the `attendance.enabled` switch.
- LIVE-1 and LIVE-2: the go-live checklists (04 §16).

## Related

- [ADR-0001](0001-a-side-is-a-section-of-one-shop.md) · A side is a section of one shop
- [ADR-0029](0029-demo-is-separate-with-fake-data-only.md) · The demo is a separate deployment with fake data only
- Docs: spec §10, §11 · 04 §1, §16
