# CLAUDE.md

<!--
Maintainer notes. Claude Code strips HTML comments like this one before reading the file, so they cost no context.
- Sources: 03 §17 (code rules) and 04 §3 (how every task runs). Decisions live in docs/adr/.
- Keep this file short (Claude Code advises under 200 lines). Area rules live in .claude/rules/ and load only
  when Claude reads or edits matching files.
- Change it in a `docs:` commit, like any decision.
-->

A shop system for agro-vet and farm-supply shops: Swahili first, offline first, multi-shop from day one. MPC (Mabatini Pumba Center, Usa River, Arusha, Tanzania) is shop #1. One repo and one website hold every part — attendance, the Drugs side and the Foods side — each switched on in settings (ADR-0033). The repo is public and is also a portfolio: fake data only.

**Stack:** Django 6.1 + DRF, PostgreSQL 18, django-allauth (`backend/`) · Next.js 16 built as a static PWA, React 19, TypeScript strict, Dexie, Tailwind + shadcn/ui (`frontend/`) · Docker Compose + Caddy (`deploy/`).

## Where things are explained

Open these when a task needs them; don't read them all up front.
- `docs/04-build-plan.md` — the task cards (`### CORE-2 · …`) in build order. **The card is the spec for a task.**
- `docs/02-domain-model.md` — entities, rules T1–X3, worked examples E1–E10 (they become tests).
- `docs/03-architecture.md` — how it is built. `docs/01-product-spec.md` — what and why.
- `docs/adr/README.md` — one ADR per decision. Read the ADR before changing anything it covers.
- `.claude/rules/` — rules for backend, frontend, migrations, sync, ops and docs. They load when you touch those files; before creating the first file in an area, read its rule file.

## Working with Jack

- Jack builds this to learn and to show employers. Teach as you go: plain English, short sentences, and define each new term the first time you use it.
- Smallest learnable steps: one step = one idea = one commit.
- Say *why* before *how*. If the card or a doc looks wrong, say so and propose a fix — don't silently follow it and don't silently change it.
- The card names the mode (BP10):
  - **Claude-led:** you write the code and the tests; Jack reviews. Before the PR, Jack explains the change back in his own words.
  - **Jack-led:** start with a 15-minute drill on the card's **Learn** line — a short explanation, one tiny example, two or three questions; wait for Jack's answers. Then you write the tests, Jack writes the main code, and you review with hints, not answers.
- In both modes you make the commits, and **every commit waits for Jack's yes** (Git, below).

## How every task runs (04 §3.3)

1. Jack creates the task branch named on the card (04 §3.4). Sessions start in plan mode.
2. `/start-task <ID>` — read the card, check it is Ready, plan small steps that each end in a commit. No code until Jack approves the plan.
3. A card that is only a one-line table row is not Ready: offer to draft the full card first (BP2).
4. Build one step at a time, tests first where the card says. Run the tests after each step. When they are green, explain the step to Jack and commit only after his yes (Git, below).
5. Past twice the card's size? Stop. Write what blocks it in the issue and propose a split.
6. `/finish-task` — `make check`, the Done list, a review by the `reviewer` subagent, *What I learned*, the PR draft.
7. After the merge: tick the card, note the hours, then `/clear` — one task, one session (BP3).

## Commands

- `make dev` — the local stack at http://localhost:8080 (Caddy in Docker → Django and Next.js on the host)
- `make check` — everything CI runs; it must pass before any PR
- `make test` · `make fmt` · `make migrate`
- `make hooks` — once per clone: the git hooks that format and lint each commit and check its `Why:` line
- One backend test: `cd backend && uv run --env-file ../.env pytest apps/sales/tests/test_services.py -k below_floor` (`.env` points Django at the Compose database)
- Frontend: `cd frontend && pnpm test` · `pnpm gen:api` after any API change

## Git (04 §3.4–§3.5)

- Never commit on `main`. One branch per task, named on its card: `feat/core-2-tenancy-guard`.
- **You make every commit, and only after Jack says yes.** Before each commit, tell Jack in plain words: what was done (which files, and what works now), why this commit is needed, and the exact message. Then run `git commit` — Claude Code asks Jack to approve it. If he says no, ask what to change; never commit around a no.
- **Every commit has a strong reason.** One small, tested step per commit. The message is a subject line, a blank line, then a `Why:` line:
  ```
  feat(core): tenancy guard raises without a shop

  Why: a query that forgets its shop must fail loudly, not return another shop's rows (ADR-0022).
  ```
  If you can't give a strong reason, don't commit — fold the change into the step it belongs to.
- Subject: `type(scope): what it does, in the present tense`. Types: feat, fix, test, refactor, docs, chore, ci, build, perf. Scope: the app or area (core, people, sync, sales, frontend, deploy…).
- Stage only what belongs together. Never skip the git hooks (`--no-verify`).
- No force-push and no rebasing of pushed work. Bring `main` in with `git merge origin/main`. Jack pushes, opens the PR and merges.
- The PR title is a conventional commit too: it becomes the one squash commit on `main` and a changelog line.

## Rules that are never broken

These protect money, history and each shop's privacy. If a task seems to need breaking one, stop and ask Jack.
1. **Tenancy.** Every model has `shop` (except `User`, `Unit` and infrastructure tables), and every query goes through the scoped manager, which fails closed. `system_context()` only in system jobs and commands, never in request code. (ADR-0022)
2. **Ledgers are append-only.** Stock movements, balance entries, allocations, attendance events, audit events, the change log, payments, money movements and dated-rule rows (prices, costs, settings, pay rates) are written only by posting services and never updated or deleted. Fixes are new rows; payments, money movements and attendance events can only be voided. (ADR-0008, ADR-0021)
3. **Exact numbers.** Money and quantities are `Decimal` in Python, big.js in TypeScript and strings in JSON — never floats. Round only with the shared rounding function. (ADR-0024)
4. **Logic lives in services and calculations only.** Views, serializers, `save()` and signals stay thin. (ADR-0015)
5. **Two data paths.** Counter screens use Dexie only; office screens use the API client only. (ADR-0019, ADR-0020)
6. **A new offline document type needs all four:** a server handler, a schema version, the device side, and tests on both sides.
7. **Nothing is deleted.** Cancel, void, suspend or archive — always with who, when and why. Foreign keys use `on_delete=PROTECT`.
8. **Generated files are never edited by hand:** `frontend/src/api/schema.d.ts` (`pnpm gen:api`), `CHANGELOG.md` (release-please), `uv.lock` and `pnpm-lock.yaml` (`uv add`, `pnpm add`). (ADR-0025)
9. **Migrations** are read line by line, and once on `main` they are never edited — write a new one. No `migrate` on any database before PPL-1 is merged. (ADR-0012)
10. **Real shop data never enters the repo:** no real names, phones, debts or prices in code, tests, seeds, docs or commits. Real sheets stay in `private/` (gitignored). Never read or print `.env`.
11. **UI text** lives in `frontend/messages/sw.json` and `en.json`; the API sends error codes, not sentences. (ADR-0032)
12. **A new dependency** needs Jack's yes first, with the reason; add it with `uv add` or `pnpm add`.

## Comments

- Every file starts with a header comment: what it is for and what it owns.
- Write many comments, and make each one explain *why* — this code is also Jack's study material: every lock, rule, edge case and trade-off. Name the rule or ADR a comment protects (`# B1: an allocation never exceeds what is open`).
- Basics of Python, TypeScript or a library are explained to Jack in the chat, not in the code.
- Keep comments true: change them in the same commit as the code.

## Done means (04 §3.2)

- [ ] Every *Done when* box on the card is ticked; the tests pass in CI; worked examples have their named tests.
- [ ] Header and why-comments everywhere; import-linter passes; services and calculations keep ≥ 90% coverage.
- [ ] Migrations read line by line; `makemigrations --check` is clean.
- [ ] The API schema and TypeScript types are regenerated, with no difference.
- [ ] New screen text is in `sw.json` and `en.json`, and Jack has checked the Swahili.
- [ ] The demo seed covers the feature, if it needs data.
- [ ] A changed decision ships as a new ADR that supersedes the old one, plus the doc change, in a `docs:` commit.
- [ ] The PR has *What I learned* in Jack's words and the hours; it is squash-merged with green CI; the card is ticked in 04.

## Claude Code setup

- `.claude/settings.json` — sessions start in plan mode; every commit, push, PR, merge, migration and new dependency asks Jack first; `.env` and `private/` are off limits.
- `.claude/hooks/guard.py` — refuses the expensive mistakes: editing generated files or migrations already on `main`, `migrate` before PPL-1, committing on `main`, skipping git hooks, force-pushing, pushing to `main`, force-adding ignored files.
- Skills `/start-task <ID>` and `/finish-task`; the read-only `reviewer` subagent.
