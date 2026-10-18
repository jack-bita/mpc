---
status: accepted
date: 2026-10-17
source: "02-domain-model.md §2 — D13"
standing: decided
cost-to-change: medium
---

# ADR-0013 · Every rule is a dated setting

## Context

Rates, fines, cut-off times and tolerances change, and a change applies from a date forward (spec principle 10). Changing a rule must never change history.

## Decision

Every rule is a `Setting` row: a key from a registry in code (type, default, scope, description), a value and an `effective_from` date. The row in force on a date is the latest on or before it; a side row beats a shop row. Rows are insert-only, and records copy the rule values they used.

## Consequences

- **Good:** One mechanism for every rule.
- **Good:** Devices receive future-dated rows and switch on the right day, even offline.
- **Cost:** Every rule read needs a date; the registry must be kept tidy.

## Alternatives considered

- **Rules as constants in code** — every change needs a deploy.
- **An editable settings table** — changing a value rewrites history.

## Enforced by

- CORE-4: `test_latest_row_on_or_before_date_wins`, `test_future_row_ignored_until_its_day`, `test_setting_type_checked`.
- SHOP-3: the settings screen adds a new dated value, never edits one.
- CORE-3: setting rows are insert-only in the database.

## Related

- [ADR-0021](0021-posting-services-and-append-only-ledgers.md) · Posting services write the ledgers; the database refuses edits
- [ADR-0010](0010-the-stock-number-never-blocks-a-real-sale.md) · The stock number never blocks a real sale
- Docs: 02 §4 Setting · 03 §5.8
