---
status: accepted
date: 2026-10-18
source: "04-build-plan.md §2 — BP16"
standing: default
cost-to-change: low
revisit: "before R3, or before accepting a first outside contribution"
---

# ADR-0034 · No open-source licence yet

## Context

The repo is public from day one for the portfolio. The product may be sold to other shops later, and code released under an open licence stays open forever.

## Decision

Public repo, all rights reserved, with one line in the README saying so. No `LICENSE` file for now.

## Consequences

- **Good:** The only reversible choice: a licence can be added later; it can't be taken back.
- **Cost:** Others may read the code but not reuse it; an outside contribution needs a licence first.

## Alternatives considered

- **A permissive licence now (MIT or Apache-2.0)** — invites reuse, but can't be withdrawn for code already released.
- **A copyleft licence (GPL or AGPL)** — keeps copies open, also can't be undone, and may complicate selling the product.
- **A private repo** — no portfolio value.

## Enforced by

- FOLIO-1: the README states "all rights reserved".
- REPO-1: no `LICENSE` file.

## Related

- [ADR-0029](0029-demo-is-separate-with-fake-data-only.md) · The demo is a separate deployment with fake data only
- Docs: 04 §2 BP16, §20 #8

## Notes

- Cost to change: low now — but granting a licence is permanent.
