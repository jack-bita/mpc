---
status: accepted
date: 2026-10-17
source: "02-domain-model.md §2 — D9"
standing: decided
cost-to-change: medium
---

# ADR-0009 · Stock leaves when goods are handed over

## Context

On the Foods side, payment and handover are separate steps and customers may collect later; on the Drugs side one person does everything (spec §3). Loaders may have no device.

## Decision

Stock leaves at handover. For a normal sale that is the moment it is confirmed; "collect later" holds the stock until pickup. MPC's own ingredients in a job leave when the job starts.

## Consequences

- **Good:** The system matches the shelf.
- **Good:** It works even if loaders have no device.
- **Cost:** "Waiting to be collected" must be shown, and available = on hand − waiting (R2).

## Alternatives considered

- **Stock leaves at payment** — wrong when a customer pays now and collects later.
- **Stock leaves when a loader taps "handed over"** — fails when loaders have no device.

## Enforced by

- SALE-4: on the one-screen flow, confirming is handing over.
- R2 FLOW epic: collect later and handover per line.

## Related

- [ADR-0003](0003-a-sale-belongs-to-one-side-a-bill-groups-sales.md) · A sale belongs to one side; a bill groups sales
- [ADR-0010](0010-the-stock-number-never-blocks-a-real-sale.md) · The stock number never blocks a real sale
- Docs: 02 §7, §14
