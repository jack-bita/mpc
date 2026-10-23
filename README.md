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

## Run it locally

The app and its API answer at one address, `http://localhost:8080`, as in production: Caddy sends `/api/` to Django and everything else to Next.js ([ADR-0017](docs/adr/0017-one-address-session-cookies-allauth.md)). PostgreSQL 18 and Caddy run in Docker; Django and Next.js run on your machine, so code changes reload at once.

**You need:** Git, make, Docker with Compose v2 (on Windows: Docker Desktop with WSL integration turned on for your Linux distro), [uv](https://docs.astral.sh/uv/) (it installs Python 3.14 itself), and Node.js 24 or newer with pnpm.

```bash
git clone https://github.com/jack-bita/mpc.git
cd mpc
cp .env.example .env              # local settings, with safe development values
(cd frontend && pnpm install)     # the frontend's packages
make hooks                        # git hooks: format and lint each commit, and check its message
make dev                          # PostgreSQL + Caddy in Docker, then Django and Next.js
```

Open <http://localhost:8080> to see *Karibu*, and <http://localhost:8080/api/health/> for `{"status":"ok","version":"dev"}`. The first `make dev` takes longer: Docker downloads two images and uv installs the backend's packages.

**Stop:** Ctrl-C stops Django and Next.js; `make down` stops the containers and keeps the database.

**Other commands:** run `make` to list them. `make check` runs everything CI runs; it must pass before every pull request.

**If something goes wrong**
- *`docker: command not found` inside WSL:* start Docker Desktop and wait for "Engine running"; then check Settings → Resources → WSL integration.
- *`port is already allocated` for 5433:* another program holds that port. Set a free one as `DB_PORT` in `.env`.
- *Django says "You have unapplied migrations… run migrate":* ignore it for now. The first migration comes with PPL-1, and `make migrate` refuses until then on purpose ([ADR-0012](docs/adr/0012-one-person-is-one-user.md)).

## How it is built

Each task gets one issue, one branch and one pull request. CI runs on the pull request, and it is squash-merged into `main`. I build it with Claude Code as a pair programmer. I approve every commit, and every pull request ends with what I learned.

## Licence

All rights reserved; see [ADR-0034](docs/adr/0034-no-open-source-licence-yet.md). You are welcome to read the code, but please ask before you reuse it.
