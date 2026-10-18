---
status: accepted
date: 2026-10-17
source: "02-domain-model.md §2 — D10"
standing: default
cost-to-change: low
revisit: "when daily counts (STK-12) are routine and negative-stock flags are rare"
---

# ADR-0010 · The stock number never blocks a real sale

## Context

Stock records start imperfect: full counts are rare and spillage is normal (spec §3). A shop that can't record a real sale stops using the system.

## Decision

Negative stock is allowed. The sale screen warns at once, and a flag is raised if the stock is still negative at day close. A setting (`stock.block_negative`, off) can change this later.

## Consequences

- **Good:** Selling never stops because of a data problem.
- **Good:** Negative stock points at counting errors to fix.
- **Cost:** Stock can be wrong for a while; the flags must be reviewed.

## Alternatives considered

- **Block the sale** — staff work around the system, or stop using it.

## Enforced by

- STK-8: a warning at once, a flag at day close.
- CORE-4: the `stock.block_negative` setting, off by default.

## Related

- [ADR-0013](0013-every-rule-is-a-dated-setting.md) · Every rule is a dated setting
- [ADR-0009](0009-stock-leaves-when-goods-are-handed-over.md) · Stock leaves when goods are handed over
- Docs: 02 §2
