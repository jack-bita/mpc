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

- **Counter screens** (`src/app/(counter)/…`: sale, payment, repayment, quick customer, drawer, clock-in) read Dexie with live queries and save documents with `saveDocument()`. They never call the API, and they behave the same online and offline. A save tells the sync by itself; *Tuma sasa* asks for one with `askToSendNow()` (`src/offline/sync/asks.ts`, which calls nothing). The sync runs beside every page, at its own moments (`src/offline/sync/triggers.tsx`, in the root layout), one tab at a time (SYNC-9).
- **Who is at the counter** (SYNC-11): a counter screen reads `usePersonAtCounter()` (`src/features/login/at-the-counter.ts`), a note the home page writes in the tab's memory, never `me`. The frame (`src/app/(counter)/counter-frame.tsx`) shows a screen only to someone it names, and its *Toka* asks the home page to log them out (`askToLeave`). A record the server refused shows with `NeedsAttention` (`src/app/(counter)/needs-attention.tsx`): a new kind of record adds its name to `whatItWas`.
- **Office screens** (`src/app/(office)/…`) use TanStack Query and the typed client in `src/api/client.ts`, through `answerOf()` (`src/api/refusal.ts`), which throws a refusal so TanStack sees it; `ApiErrorAlert` shows it. Offline they show *Inahitaji mtandao*.
- A lint rule refuses `src/api/`, `@tanstack/*`, `openapi-fetch`, `fetch`, `XMLHttpRequest`, `WebSocket`, `EventSource` and `navigator.sendBeacon` in `src/app/(counter)/` (`import-rule.test.ts`); tests there may watch `fetch`, never import `src/api/`. It reads a screen's own code only: a shared part that calls the server, imported by a counter screen, and a dynamic `import()` of a package, need review to catch them (UI-2). Screens that log in call the server, so they live outside `(counter)/`. The store of server answers is shared by everyone on a device: empty it at each login, logout and quick switch with `forgetTheLastPerson` (`src/api/query-client.ts`), never `clear()`, which leaves a screen on show with the last person's answer (UI-4); it keeps a change still on its way in its place in the queue, as one dropped goes on trying all the same (SYNC-10). Every change waits in one queue (`CHANGES_IN_ORDER`, the store's default scope), sent one at a time in the order made, offline too, so a logout always goes after the changes made before it; a password form's change sets `gcTime: 0`, so no password stays in the store (UI-5).
- allauth's password routes (`/_allauth/browser/v1/`) are outside the API's description: call them with `callAllauth` (`src/api/allauth.ts`), which sends the CSRF token, throws `NoConnection` with no answer, and reads allauth's own answer into the same `ApiRefusal`, so `ApiErrorAlert` and `apiFieldMessages` show it. A route's bare 401 or 409 is named by the form that calls it (UI-5).

## Numbers and text

- Money and quantities go through `src/lib/decimal.ts` (big.js); round only with `src/lib/rounding.ts`. Both pass `shared/test-vectors/`. No plain `number` arithmetic on money.
- Whoever is logged in sees their own language and font; nobody, the laptop's own (UI-9). A screen that learns who is here calls `useFollowThePerson(here)` (`src/features/people/follow-the-person.ts`) with the person it shows, as both frames do: it opens their language with `setPersonsLanguage`, in memory only, and sets their font on `<html>` (`data-font`). `setLanguage` is the laptop's own, from the bar's button, which shows only while nobody is logged in (Jack's choice). A person's choices change only in *Mipangilio yangu* (`PATCH /api/auth/me/settings/`).
- Times of day are shown with `formatTime` (`src/lib/format.ts`): `07:55`, 24 hours, in the shop's zone, never Swahili time (Jack, SYNC-11).
- Money is shown with `formatMoney` (`Intl.NumberFormat('sw-TZ')`, TZS without decimals); stock with `formatStock`, in each book's order: "mifuko 26 + kilo 35.5" in Swahili, "26 mifuko + 35.5 kilo" in English (`src/lib/format.ts`).
- No visible string literals: every string is a use-intl key (`useTranslations()`, ADR-0040) in `messages/sw.json` and `en.json`, Swahili first; lint rules refuse a word typed into a screen or into `aria-label`, `aria-description`, `placeholder`, `title` or `alt`, and `language.test.tsx` opens every page in English. API error codes map to translated messages: `errors.<code>` in both books, nested by the code's dots (`errors.pin.locked`), turned into its sentence by `codeMessage()` (`src/i18n/codes.ts`, outside the counter lock, so sync's codes can use it too); office screens show a failed call with `useApiErrorWords()` (`src/api/errors.ts`). `errors.test.ts` lists every code the API sends: a new code adds its line there and its two sentences (UI-2). Tests render a screen with `src/test/render.tsx`, which gives it the word books.

## Generated and vendored code

- `shared/openapi.json` and `src/api/schema.d.ts` come from `pnpm gen:api` — never edit them; commit both. CI fails if either is stale (`pnpm check:api`, and a backend test).
- `src/components/ui/` comes from shadcn (`pnpm shadcn add <name>`, a download: ask first). Never edit shadcn's files there (`guard.py` refuses it); Prettier skips the folder, and its `README.md` is its header.

## The look (ADR-0039)

- Screens use only our pieces in `src/components/design/` (Button, ButtonLink, Field, PasswordField, Input, Label, Choice, Card, Alert, SideBand, TopBar). ButtonLink is a real link with the button's classes, as Base UI's button must not be a link; Choice is a big row per option, over shadcn's radio-group (UI-3), and a row may name its own `lang` and `font` (UI-9). Every password box is a PasswordField, whose eye shows and hides what is typed, in Field's `end` slot (UI-5). Only `components/design/` imports `components/ui/`: a lint rule refuses it anywhere else (`import-rule.test.ts`).
- A new shadcn part gets a piece of ours in `components/design/`, with its test, before a screen uses it. Read what `shadcn add` changed: if it writes greys or chart and sidebar tokens into `globals.css`, `tokens.test.ts` fails — remove them.
- Colours, corners and heights come from the tokens in `globals.css`, never a value of a screen's own. Heights are written `h-(--control-big)`, a spelling `cn()` knows is a height.
- Focus rings at full strength (`ring-ring`, never `ring-ring/50`); on green, the ring is white: anything green uses `ON_GREEN` from `top-bar.tsx`, which sets `--ring`, and only the button's `bar` kind sits on it (UI-1).
- Counter, office and setup screens live in `src/app/(counter)/`, `src/app/(office)/` and `src/app/(setup)/`, whose layouts wrap them in `AppFrame` (the top bar and the page's one `<main>`): a screen there doesn't write its own `<main>`. The setup area holds what a device does before it belongs to a shop (Sajili kifaa hiki); it calls the server, so it is outside the counter lock (UI-3). The home page `/` of a registered device is the PIN login (`src/features/login/at-the-device.tsx`), in AppFrame's `login` area, whose bar names the person and the side they work on (UI-4). Its tiles read the laptop's copy of the staff, so they show offline (`staff-picker.tsx`); with no network, no answer, or a logout not heard yet, the PIN is checked on the laptop (`checkPinOffline`, `src/offline/pin.ts`), and someone let in that way is `useOfflinePerson()` (`src/features/login/offline-session.ts`), a session in the tab's memory only, which a block, a sync's suspension or a new PIN ends (SYNC-10). The password pages live in `src/app/(login)/` (login, forgot password, the email link's page), in the same area. The office layout is `OfficeFrame` (`src/features/office/office-frame.tsx`): the person, their shop and *Toka* in the bar, anyone not logged in sent to the way in, a registered laptop's idle lock, and *Chagua nenosiri lako* in place of the screen for a temporary password; a new office screen adds its button to the office's home page (`office-home.tsx`) (UI-5). *Mipangilio yangu* (`/my-settings/`) has a button there for everyone, and on the PIN home's welcome (UI-9).
- The device knows itself through `src/features/devices/this-device.ts` (its saved copy, `mpc.device`, which never calls the server, so any screen may read it) and `device-check.tsx` (which asks the server, on every page). A `device.blocked` from any call through the store locks the app (`DeviceLock`), so send every screen's call through TanStack Query; sync's pull and push run outside the store, so each calls `saveBlocked()` itself (UI-3, SYNC-7 to SYNC-9).

## Screens

- Laptops are keyboard first (`/` focuses search, Enter adds); phones get big tap targets and a numeric keypad for cash and kg.
- Budgets: counter code under 300 KB compressed, per counter page, checked after the build by `frontend/scripts/counter-budget.mjs` in `make check-frontend` (SYNC-11: `/attendance/` 234.6 KB, nearly all shared); confirming a sale under 0.3 s; search under 50 ms for 5,000 products.

## Tests and commands

- Vitest + Testing Library + fake-indexeddb, next to the code (`*.test.ts(x)`); Next.js's router is a stand-in in every test (`src/test/router.ts`, set up in `vitest.setup.ts`), which a test reads to see where a screen sent the person (UI-5); Playwright in `frontend/e2e/`, against the backend image — it can switch the browser offline.
- Scripts: `pnpm dev`, `pnpm build`, `pnpm test`, `pnpm lint` (ESLint with no warnings allowed, then a Prettier check), `pnpm format`, `pnpm typecheck` (REPO-3); `pnpm gen:api` and `pnpm check:api` (UI-2); `pnpm e2e` (UI-6).
