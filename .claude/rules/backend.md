---
paths:
  - "backend/**"
---

# Backend rules — Django + DRF

<!-- Source: 03 §5, §9, §11. Loads when Claude reads or edits a file under backend/. -->

## Apps and layers (ADR-0035)

An app imports only from lower layers; import-linter checks it in CI.

| Layer | Apps |
|---|---|
| 0 | `core`, `control` — `control` may import `core` |
| 1 | `shops` |
| 2 | `people` |
| 3 | `catalog`, `contacts` |
| 4 | `inventory`, `money` — `inventory` may import `money` |
| 5 | `sales`, `services`, `staffpay` — `services` may import `sales` |
| 6 | `sync`, `reports` |

Every app may import `control`; `control` imports only `core`. A model may name a higher-layer model by string (`"sales.Sale"`) — that is not an import.

## Inside an app

`models.py` tables and every rule the database can enforce · `services.py` every write, one function per action, each in a transaction · `selectors.py` every read the API and reports use · `calculations.py` pure functions, mirrored in TypeScript · `documents.py` handlers for offline document types · `permissions.py` · `tasks.py` background tasks, which with management commands are the only code that may open every shop (03 §5.11) · `api/` thin serializers, views and urls · `admin.py` · `tests/`

## Writing services

- Take explicit arguments (who, which device, which shop) and return results. Raise domain errors with codes (`sale.below_floor`); one exception handler turns them into `{"code", "message", "fields", "params"}`.
- Check that every record you link to belongs to the same shop (T1).
- Record changes for sync with `record_change` inside the same transaction.
- Posting one document is one transaction (03 §5.5): the document → rule checks (online: an error; from offline: accept and raise a Flag) → payments and allocations → stock movements + `StockBalance` → debt + `ContactBalance` → flags → change log and jobs → commit.
- Locks: atomic increments for balances; lock the drawer's open session for cash; lock a contact's open debts for repayments; change-log numbers last, from the shop's `ShopSequence` row.
- Rules come from `get_setting(key, shop, side=None, on=date)`. A new key goes in the registry in `core` with its type, default, scope and description. Copy the values a record used onto the record (T4).
- Base classes from `core`: `ShopScoped`, `Editable` (a stale `version` → 409 `version_conflict`), `CounterRecord`, `AppendOnly`.

## Data conventions

- IDs are UUIDv7 (`uuid.uuid7()`). Clients send the UUID on create, so a retry can't duplicate.
- Money `numeric(14,2)`, quantities `numeric(14,3)`, times `timestamptz` in UTC; `business_date` in shop time (Africa/Dar_es_Salaam).
- Phones are stored as `+255…` through the normaliser in `core`. Generic links are a short type code + UUID.
- Indexes lead with `shop`.

## API (03 §5.10)

- Office REST under `/api/v1/<app>/` (staff session); sync under `/api/sync/v1/` (device key); PIN login under `/api/auth/`; passwords through allauth at `/_allauth/browser/v1/`.
- snake_case JSON; money and quantities as strings; ISO 8601 UTC times; cursor pagination; throttles on login, PIN and pairing.
- Office routes build on `ShopViewSet` (`apps/core/api/base.py`): rows come from `get_queryset()` on each visit, never a class-level `queryset`. A create adds `CreateOnceMixin` (the client's UUIDv7 makes it safe to send twice), an edit adds `EditMixin` (PATCH with `version`). Name where rows keep their side in `side_field` (None for rows of the whole shop). Refusals reach the app through the one error handler (`apps/core/api/errors.py`).
- After changing a serializer or a view, regenerate the schema and the TypeScript types (`cd frontend && pnpm gen:api`).
- A breaking change gets a `v2` route beside `v1` while devices update.

## Tests (03 §11)

- pytest + pytest-django on real PostgreSQL, never SQLite; factory_boy; Hypothesis for ledger properties.
- Names state the rule: `test_pin_lockout_doubles`. Worked examples: `test_e5_debt_clears_oldest_first`. Spec §8.1 rows: `test_arrives_0750_full_day_minus_fine`.
- Calculations also pass `shared/test-vectors/*.json` (inputs and outputs as strings), the same files Vitest runs.
- Every bug fix adds a test. The tenancy sweep (`backend/tests/test_tenancy_sweep.py`) is never loosened, nor edited, to let a table, a route or a file pass. What grows instead: in `backend/tests/conftest.py`, a row of each new route's table for the sweep's two shops, with values only shop A has, and the query parameters a route needs (`sweep_queries`); in `backend/tests/sweep_lists.py`, only by a decision written on the card, the allowed lists: a table with no `shop`, a route under `api/` that reads no shop's table, a route whose answers the sweep can't read, with its own leak test (`OWN_LEAK_TESTS`), a file that builds a query by hand (`HAND_BUILT_QUERIES`), and a file that runs SQL by hand outside migrations, system jobs and tests (`RAW_SQL`: today only `apps/core/acting.py`, which tells PostgreSQL who acts, CTRL-2). Teaching the sweep something new, such as calling a route that reads shop tables with a device's key (pairing, PIN login, sync), or a new kind of allowed list, as `RAW_SQL` was, is a new check, added in a reviewed change.
- The edit history's check (`backend/tests/test_edit_history.py`, ADR-0036) finds by itself every shop table that is not a ledger: each must carry the `record_edits` trigger, switched on, with its type code from `apps/core/links.py`. A table that keeps its history another way goes on `NO_EDIT_HISTORY` in `backend/tests/sweep_lists.py`, with its reason, only by a decision written on the card.

## Privacy

- Logs are JSON lines with request id, shop, side, device and staff id — never names, phone numbers or amounts.
- Buying prices, PIN hashes and passwords never leave the server; payslips never go to shared devices.
