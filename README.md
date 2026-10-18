# MPC — a shop system for agro-vet and farm-supply shops

An offline-first, Swahili-first system for the counter and the office: staff attendance and pay, selling, payments (cash, bank, Lipa Namba), credit (*madeni*) and stock. It is built first for **MPC — Mabatini Pumba Center**, a family agro-vet shop in Usa River, Arusha, Tanzania, and designed from day one for other shops too.

**Status:** in development. The planning is done; the code starts with stage 0 of the build plan.

## Start here

| Read | For |
|---|---|
| [Product spec](docs/01-product-spec.md) | What it does, and why |
| [Domain model](docs/02-domain-model.md) | The entities and the business rules |
| [Architecture](docs/03-architecture.md) | How it is built |
| [Build plan](docs/04-build-plan.md) | Every task, in order |
| [Decisions](docs/adr/README.md) | One short record for each big decision |
| [CLAUDE.md](CLAUDE.md) | How the code is written |

## Stack

Django 6.1 + Django REST Framework · PostgreSQL 18 · Next.js 16 as a static PWA · React 19 · TypeScript · Dexie (IndexedDB) · Docker Compose + Caddy

## How it is built

Each task gets one issue, one branch and one pull request. CI runs on the pull request, and it is squash-merged into `main`. I build it with Claude Code as a pair programmer. I approve every commit, and every pull request ends with what I learned.

## Licence

All rights reserved; see [ADR-0034](docs/adr/0034-no-open-source-licence-yet.md). You are welcome to read the code, but please ask before you reuse it.
