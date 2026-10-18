# Architecture Decision Records

An ADR is a short record of one big decision: the context, what we chose, what it costs, and what we didn't choose. **Read the ADR before changing anything it covers.**

- How we write them: [ADR-0000](0000-record-decisions-as-adrs.md) · a new one starts from [template.md](template.md).
- **Numbers:** 0001–0014 = domain model D1–D14 · 0015–0032 = architecture AD1–AD18 · 0033 = build plan BP7 · 0034 = BP16. A new decision takes the next number.
- **Standing:** `confirmed` = Jack confirmed it · `decided` = agreed in the planning pack · `default` = best guess, safe to change while building.
- **Cost:** how hard the decision is to undo later.
- **Changing one:** never rewrite an accepted ADR — write a new one that supersedes it (ADR-0000).

| ADR | Decision | From | Standing | Cost |
|---|---|---|---|---|
| [0000](0000-record-decisions-as-adrs.md) | Record decisions as ADRs | portion 5 | decided | low |
| [0001](0001-a-side-is-a-section-of-one-shop.md) | A side is a section of one shop | D1 | confirmed | high |
| [0002](0002-stock-is-kept-per-stock-location.md) | Stock is kept per stock location | D2 | decided | high |
| [0003](0003-a-sale-belongs-to-one-side-a-bill-groups-sales.md) | A sale belongs to one side; a bill groups sales | D3 | confirmed | high |
| [0004](0004-credit-is-the-unpaid-part-of-a-confirmed-sale.md) | Credit is the unpaid part of a confirmed sale | D4 | decided | high |
| [0005](0005-repayments-clear-the-oldest-debt-first.md) | Repayments clear the oldest debt first | D5 | confirmed | high |
| [0006](0006-anything-charged-to-a-customer-is-a-sale.md) | Anything charged to a customer is a sale | D6 | decided | medium |
| [0007](0007-ids-and-numbers-are-made-on-the-device.md) | IDs and numbers are made on the device | D7 | decided | high |
| [0008](0008-documents-in-ledgers-out.md) | Documents in, ledgers out | D8 | decided | high |
| [0009](0009-stock-leaves-when-goods-are-handed-over.md) | Stock leaves when goods are handed over | D9 | decided | medium |
| [0010](0010-the-stock-number-never-blocks-a-real-sale.md) | The stock number never blocks a real sale | D10 | default | low |
| [0011](0011-profit-uses-the-last-buying-price.md) | Profit uses the last buying price | D11 | default | low |
| [0012](0012-one-person-is-one-user.md) | One person is one user | D12 | decided | high |
| [0013](0013-every-rule-is-a-dated-setting.md) | Every rule is a dated setting | D13 | decided | medium |
| [0014](0014-practice-mode-is-a-separate-practice-shop.md) | Practice mode is a separate practice shop | D14 | decided | low |
| [0015](0015-a-modular-monolith.md) | A modular monolith | AD1 | decided | high |
| [0016](0016-the-shop-app-is-a-static-pwa-built-with-next-js.md) | The shop app is a static PWA built with Next.js | AD2 | decided | medium |
| [0017](0017-one-address-session-cookies-allauth.md) | One web address, session cookies, and django-allauth for passwords | AD3 | confirmed | medium |
| [0018](0018-two-kinds-of-identity-devices-and-people.md) | Two kinds of identity: devices and people | AD4 | decided | high |
| [0019](0019-offline-data-lives-in-indexeddb-through-dexie.md) | Offline data lives in IndexedDB, through Dexie | AD5 | decided | medium |
| [0020](0020-sync-push-documents-pull-changes.md) | Sync = push documents, pull changes | AD6 | decided | high |
| [0021](0021-posting-services-and-append-only-ledgers.md) | Posting services write the ledgers; the database refuses edits | AD7 | decided | high |
| [0022](0022-tenancy-in-one-place-rls-later.md) | Tenancy is enforced in one place; row-level security comes later | AD8 | default | medium |
| [0023](0023-postgresql-only-no-redis.md) | PostgreSQL is the only data store in R1; no Redis | AD9 | default | low |
| [0024](0024-exact-numbers-everywhere.md) | Exact numbers everywhere | AD10 | decided | high |
| [0025](0025-the-api-contract-is-generated.md) | The API contract is generated | AD11 | decided | low |
| [0026](0026-search-runs-on-the-device.md) | Search runs on the device | AD12 | decided | low |
| [0027](0027-one-linux-server-with-docker-compose.md) | The real shop runs on one Linux server, with Docker Compose | AD13 | decided | medium |
| [0028](0028-real-shop-data-stays-in-tanzania.md) | Real shop data stays in Tanzania, on a Lineserve server in Dar es Salaam | AD14 | confirmed | medium |
| [0029](0029-demo-is-separate-with-fake-data-only.md) | The demo is a separate deployment with fake data only | AD15 | decided | low |
| [0030](0030-foods-hand-off-cashier-only-offline.md) | Foods hand-off: through the server with a network, cashier-only without | AD16 | confirmed | low |
| [0031](0031-web-address-fixed-before-first-device.md) | The web address is fixed before the first device is registered | AD17 | decided | high |
| [0032](0032-ui-text-lives-in-the-app-the-api-sends-codes.md) | UI text lives in the app; the API sends codes | AD18 | decided | low |
| [0033](0033-one-website-attendance-first.md) | One website with everything, built one part after another: attendance first | BP7 | confirmed | medium |
| [0034](0034-no-open-source-licence-yet.md) | No open-source licence yet | BP16 | default | low |
