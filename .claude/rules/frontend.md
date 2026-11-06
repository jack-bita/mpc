---
paths:
  - "frontend/**"
---

# Frontend rules — Next.js as a static PWA

<!-- Source: 03 §6–§8, §14. Loads when Claude reads or edits a file under frontend/. -->

## A static app (ADR-0016)

- `output: 'export'`: plain files, no Node server in production.
- Every page is a client component. No server components at runtime, no server actions, no middleware, no route handlers, no image optimisation (`images.unoptimized`).
- A file that asks use-intl for words (`useTranslations`) starts with `"use client"`. The area layouts are built as server components, and a part they import without the line stops `next build` at the first page in an area ("createContext is not a function"); no Vitest test sees it, so `use-client.test.ts` reads the files (UI-1).
- No dynamic `[id]` pages for records: use a query string (`/sales/view?id=…`).

## Two data paths — the main rule

- **Counter screens** (`src/app/(counter)/…`: sale, payment, repayment, quick customer, drawer, clock-in) read Dexie with live queries and save documents with `saveDocument()`. They never call the API, and they behave the same online and offline.
- **Office screens** (`src/app/(office)/…`) use TanStack Query and the typed client in `src/api/client.ts`, through `answerOf()` (`src/api/refusal.ts`), which throws a refusal so TanStack sees it; `ApiErrorAlert` shows it. Offline they show *Inahitaji mtandao*.
- A lint rule refuses `src/api/` and `@tanstack/*` in `src/app/(counter)/` (`import-rule.test.ts`). It reads a screen's own imports only: a shared part that calls the server, imported by a counter screen, needs review to catch it (UI-2).

## Numbers and text

- Money and quantities go through `src/lib/decimal.ts` (big.js); round only with `src/lib/rounding.ts`. Both pass `shared/test-vectors/`. No plain `number` arithmetic on money.
- Money is shown with `formatMoney` (`Intl.NumberFormat('sw-TZ')`, TZS without decimals); stock with `formatStock`, in each book's order: "mifuko 26 + kilo 35.5" in Swahili, "26 mifuko + 35.5 kilo" in English (`src/lib/format.ts`).
- No visible string literals: every string is a use-intl key (`useTranslations()`, ADR-0040) in `messages/sw.json` and `en.json`, Swahili first; lint rules refuse a word typed into a screen or into `aria-label`, `aria-description`, `placeholder`, `title` or `alt`, and `language.test.tsx` opens every page in English. API error codes map to translated messages: `errors.<code>` in both books, nested by the code's dots (`errors.pin.locked`), turned into its sentence by `codeMessage()` (`src/i18n/codes.ts`, outside the counter lock, so sync's codes can use it too); office screens show a failed call with `useApiErrorWords()` (`src/api/errors.ts`). `errors.test.ts` lists every code the API sends: a new code adds its line there and its two sentences (UI-2). Tests render a screen with `src/test/render.tsx`, which gives it the word books.

## Generated and vendored code

- `shared/openapi.json` and `src/api/schema.d.ts` come from `pnpm gen:api` — never edit them; commit both. CI fails if either is stale (`pnpm check:api`, and a backend test).
- `src/components/ui/` comes from shadcn (`pnpm shadcn add <name>`, a download: ask first). Never edit shadcn's files there (`guard.py` refuses it); Prettier skips the folder, and its `README.md` is its header.

## The look (ADR-0039)

- Screens use only our pieces in `src/components/design/` (Button, Field, Input, Label, Card, Alert, SideBand, TopBar). Only `components/design/` imports `components/ui/`: a lint rule refuses it anywhere else (`import-rule.test.ts`).
- A new shadcn part gets a piece of ours in `components/design/`, with its test, before a screen uses it. Read what `shadcn add` changed: if it writes greys or chart and sidebar tokens into `globals.css`, `tokens.test.ts` fails — remove them.
- Colours, corners and heights come from the tokens in `globals.css`, never a value of a screen's own. Heights are written `h-(--control-big)`, a spelling `cn()` knows is a height.
- Focus rings at full strength (`ring-ring`, never `ring-ring/50`); on green, the ring is white: anything green uses `ON_GREEN` from `top-bar.tsx`, which sets `--ring`, and only the button's `bar` kind sits on it (UI-1).
- Counter and office screens live in `src/app/(counter)/` and `src/app/(office)/`, whose layouts wrap them in `AppFrame` (the top bar and the page's one `<main>`): a screen there doesn't write its own `<main>`.

## Screens

- Laptops are keyboard first (`/` focuses search, Enter adds); phones get big tap targets and a numeric keypad for cash and kg.
- Budgets: counter code under 300 KB compressed (checked in CI); confirming a sale under 0.3 s; search under 50 ms for 5,000 products.

## Tests and commands

- Vitest + Testing Library + fake-indexeddb, next to the code (`*.test.ts(x)`); Playwright in `frontend/e2e/`, against the backend image — it can switch the browser offline.
- Scripts: `pnpm dev`, `pnpm build`, `pnpm test`, `pnpm lint` (ESLint with no warnings allowed, then a Prettier check), `pnpm format`, `pnpm typecheck` (REPO-3); `pnpm gen:api` and `pnpm check:api` (UI-2); `pnpm e2e` (UI-6).
