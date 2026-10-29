---
status: accepted
date: 2026-10-29
source: "CTRL-2, decided by Jack in chat while planning; replaces 03 §3's default, django-pghistory"
standing: confirmed
cost-to-change: medium
---

# ADR-0036 · Office edits are recorded by our own trigger, into one table

## Context

03 §5.16 wants every change to an office record kept, with the person who made it, by database triggers, so that no code path can skip it. Office records are staff members, sides, payment accounts and stock locations today, and products, contacts, roles and devices later. 03 §3 named django-pghistory as the default tool. By default that library adds one event table per tracked table, copying every column. Those tables are not built on `ShopScoped`, their links use `DO_NOTHING` instead of `PROTECT`, and they have no shop guard. Its context table, which holds who acted, has no shop at all. CORE-7's tenancy sweep refuses all of this, rightly: shop B's code could read shop A's history.

## Decision

- One append-only table, `control.EditEvent`, built on `AppendOnly` like every ledger. Each row holds the shop, who (`created_by`), when (`created_at`), the row that changed (a type code and its UUID, 03 §5.1), and the columns that changed, before and after, every value as text.
- One trigger function of our own, `control_record_edit()`, which each office table's migration puts on that table (`RecordEdits`). It runs after every UPDATE and writes a row only when something visible changed, at the edit's own time (`clock_timestamp()`). Columns that must never be copied, such as a PIN hash, are skipped.
- Only that trigger writes the table: a guard refuses any other INSERT, so neither `bulk_create` nor SQL typed by hand can add a change nobody made.
- Each office visit tells PostgreSQL who acts and its shop (`set_config('mpc.staff_id', …)` and `mpc.shop_id` in `apps/core/acting.py`), and the trigger reads both: it names the person, and refuses an edit of another shop's row (T1). A service that passes its own `by` tells PostgreSQL too. Outside a visit nobody is named: the system acted.
- Every shop table that is not a ledger keeps a history, unless a short list names it with its reason (`NO_EDIT_HISTORY`): payment accounts and stock locations too (Jack, at CTRL-2's review).
- The trigger's SQL is frozen once it is on `main`. A change is a new function (`control_record_edit_v2`), as with the ledgers' rules (ADR-0021).

## Consequences

- **Good:** The history has the shop guard, `PROTECT` links and the append-only trigger, like every other shop table, and CORE-7's sweep checks it with no exception.
- **Good:** One table serves every office table. CTRL-5's trail per record reads one place, and a change to a tracked table needs no change to the history.
- **Good:** No new package.
- **Cost:** About thirty lines of SQL that we maintain ourselves.
- **Cost:** Values are kept as text in JSON, not as typed columns.
- **Cost:** `set_config` is raw SQL in code that a visit runs, so CORE-7's sweep lists the one file allowed to run it (`RAW_SQL`).
- **Cost:** PostgreSQL 18 is needed, because the trigger makes ids with `uuidv7()`.

## Alternatives considered

- **django-pghistory** (03 §3's first default): mature and well known, but its tables lack the shop guard and `PROTECT` links, and its context table has no shop. Bending it to fit fights its defaults, and it brings two packages (django-pghistory and django-pgtrigger).
- **Services write the history in Python:** a bulk `update()`, a forgotten service or SQL typed by hand would skip it, and 03 §5.16 wants nothing to skip it.
- **Read who acted from the row's `updated_by`:** only `Editable` tables have that column. A write that forgot to set it would name the previous editor, which is worse than naming nobody.

## Enforced by

- CTRL-2: `test_every_office_table_records_its_edits` (every shop table that is not a ledger has the trigger, built right, with its type code, and copies no secret column), `test_history_rows_append_only`, `test_only_the_trigger_writes_history`, `test_edit_of_another_shops_row_refused`, `test_edit_trigger_sql_never_changes_once_on_main`.
- CORE-7's tenancy sweep, which checks `control.EditEvent` like every shop table.

## Related

- [ADR-0021](0021-posting-services-and-append-only-ledgers.md) · Posting services write the ledgers; the database refuses edits
- [ADR-0022](0022-tenancy-in-one-place-rls-later.md) · Tenancy is enforced in one place; row-level security comes later
- [ADR-0035](0035-a-modular-monolith-with-control-beside-core.md) · A modular monolith, with control beside core
- Docs: 02 §13, 03 §3, §5.4, §5.6, §5.16; 04 CTRL-2, AUTH-4
