---
status: accepted
date: 2026-10-18
source: "03-architecture.md §2 — AD10"
standing: decided
cost-to-change: high
---

# ADR-0024 · Exact numbers everywhere

## Context

Devices compute totals offline, so device and server must agree to the shilling. Floats lose shillings.

## Decision

Money and quantities travel as decimal strings in JSON, are `Decimal` in Python and big.js in TypeScript. One rounding rule — half-up to the money rounding step (default 1 shilling), per line total — is written once per language and proven equal by shared test vectors in `shared/test-vectors/`.

## Consequences

- **Good:** Device and server agree exactly; a disagreement becomes a `total_mismatch` flag, not a silent error.
- **Cost:** Every calculation must use the helpers; two implementations stay in step only through the vectors.

## Alternatives considered

- **Integer shillings or cents** — exact too, but quantities like 12.5 kg and factors like 0.1 still need decimals.
- **Floats** — 0.1 + 0.2 ≠ 0.3; totals drift.

## Enforced by

- CORE-5: `test_vectors_rounding`, and a check that stops `float` in calculation code.
- UI-1: `vectors.rounding.test.ts` runs the same vector files.
- SALE-1: sale calculations in both languages against shared vectors.

## Related

- [ADR-0025](0025-the-api-contract-is-generated.md) · The API contract is generated
- [ADR-0008](0008-documents-in-ledgers-out.md) · Documents in, ledgers out
- Docs: 02 M1 · 03 §8
