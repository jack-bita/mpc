---
paths:
  - "frontend/**"
---

# Frontend rules — Next.js as a static PWA

<!-- Source: 03 §6–§8, §14. Loads when Claude reads or edits a file under frontend/. -->

## A static app (ADR-0016)

- `output: 'export'`: plain files, no Node server in production.
- Every page is a client component. No server components at runtime, no server actions, no middleware, no route handlers, no image optimisation (`images.unoptimized`).
- No dynamic `[id]` pages for records: use a query string (`/sales/view?id=…`).

## Two data paths — the main rule

- **Counter screens** (`src/app/(counter)/…`: sale, payment, repayment, quick customer, drawer, clock-in) read Dexie with live queries and save documents with `saveDocument()`. They never call the API, and they behave the same online and offline.
- **Office screens** (`src/app/(office)/…`) use TanStack Query and the typed client in `src/api/client.ts`. Offline they show *Inahitaji mtandao*.

## Numbers and text

- Money and quantities go through `src/lib/decimal.ts` (big.js); round only with `src/lib/rounding.ts`. Both pass `shared/test-vectors/`. No plain `number` arithmetic on money.
- Money is shown with `Intl.NumberFormat('sw-TZ')`, TZS without decimals; stock as "26 mifuko + 35.5 kg".
- No visible string literals: every string is a next-intl key in `messages/sw.json` and `en.json`, Swahili first. API error codes map to translated messages.

## Generated and vendored code

- `src/api/schema.d.ts` comes from `pnpm gen:api` — never edit it.
- `src/components/ui/` comes from shadcn: wrap a component rather than edit it, or say why.

## Screens

- Laptops are keyboard first (`/` focuses search, Enter adds); phones get big tap targets and a numeric keypad for cash and kg.
- Budgets: counter code under 300 KB compressed (checked in CI); confirming a sale under 0.3 s; search under 50 ms for 5,000 products.

## Tests and commands

- Vitest + Testing Library + fake-indexeddb, next to the code (`*.test.ts(x)`); Playwright in `frontend/e2e/`, against the backend image — it can switch the browser offline.
- Scripts (created in REPO-3 and UI-6): `pnpm dev`, `pnpm build`, `pnpm test`, `pnpm lint`, `pnpm typecheck`, `pnpm gen:api`, `pnpm e2e`.
