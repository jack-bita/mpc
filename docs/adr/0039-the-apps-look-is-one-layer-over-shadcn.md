---
status: accepted
date: 2026-11-05
source: "Jack, while drafting the cards UI-7, UI-8 and UI-9 (04 v1.40, 03 §7.3)"
standing: confirmed
cost-to-change: low
---

# ADR-0039 · The app's look is one layer over shadcn, with its fonts inside the app

## Context

REPO-3 left shadcn's neutral placeholder colours and no font of its own, promising a card for the real look. Built on
those placeholders, the app would look like any other shadcn app, and each new screen could pick its own look. The shop
already has a look: a green godown with blue at the back, a green container for the Drugs side, and Foods bags in green
and white with faded-red stripes. Counter screens must also work with no internet, so nothing they need may come from
another server when they run.

## Decision

- **The colours come from the shop**, in this order: green first, blue second, white as the background. One faded red is
  for warnings only. They are design tokens in `src/app/globals.css`, so changing one changes every screen.
- **Every text and background pair reads at 4.5:1 or better**, the common minimum for readable text.
- **One layer over shadcn.** shadcn and Base UI give the behaviour: focus, keyboard and screen readers. They stay
  untouched in `components/ui/`. Our own pieces in `components/design/` set the look, and screens use only those.
- **Two fonts live inside the app:** Source Sans 3 by default, and Atkinson Hyperlegible Next as the second, chosen for
  easy reading. The files are in the repo, nothing fetches a font at build time or when the app runs, and the service
  worker keeps both for offline use.
- **A person's font follows the person**, as their language does (03 §7.4). It is stored by its role (`default` or
  `second`), not by the font's name.
- **Light only for now**, with one look for every shop. Both can change later (04 §20).

## Consequences

- **Good:** The app looks like the shop, and no screen can drift from it, because a lint rule keeps screens away from
  `components/ui/`.
- **Good:** The fonts work offline, and the app depends on no font server.
- **Good:** Someone who finds small letters hard to read has a real choice, and it doesn't change the screen for the
  next person on a shared laptop.
- **Cost:** Each new shadcn part needs a small piece of ours before a screen can use it.
- **Cost:** Two font files (about 63 KB) join every device's offline copy of the app.
- **Cost:** A person's font adds one field on `User`, and one more column in the staff rows sent to each device.

## Alternatives considered

- **shadcn's default look** — it is not the shop's look, and every shadcn app shares it.
- **Components built by hand** — focus, keyboard use and screen readers are easy to get wrong.
- **Fonts fetched from Google** — when the app runs this breaks offline use, and at build time it ties every build to
  another company's server.
- **A font choice kept on the device** — on a shared counter laptop, one person's choice would change the screen for
  everyone.
- **Dark mode now** — every colour needs a second shade and every screen a second check. The tokens leave the door
  open.

## Enforced by

- UI-7: `tokens.test.ts` (contrast, no placeholder left), `manifest.test.ts`, a lint rule refusing `next/font/google`.
- UI-8: `import-rule.test.ts`, `button.test.tsx`, `field.test.tsx`.
- UI-9: the database rule on `User.font`, `test_unknown_font_refused`.

## Related

- [ADR-0012](0012-one-person-is-one-user.md) · One person is one user
- [ADR-0016](0016-the-shop-app-is-a-static-pwa-built-with-next-js.md) · The shop app is a static PWA built with Next.js
- [ADR-0032](0032-ui-text-lives-in-the-app-the-api-sends-codes.md) · UI text lives in the app; the API sends codes
- Docs: 03 §7.3, §7.4; 02 §5; 04 UI-7, UI-8, UI-9, §20
