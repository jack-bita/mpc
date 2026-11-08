# Makefile: one short command per job, the same for Jack, the README and CI (REPO-4).
# It owns the commands, not the settings: those live in .env (copied from .env.example).
# Run `make` alone to list the commands. Recipe lines start with a real tab (.editorconfig).

# These names are jobs, not files: without this line, a file called `test` would stop `make test`.
.PHONY: help dev dev-backend dev-frontend down test check check-backend check-frontend build-image check-image check-e2e fmt hooks migrate
# Plain `make` shows the list of commands instead of starting something.
.DEFAULT_GOAL := help
# `make dev` starts a second make; this hides its "Entering directory" lines.
MAKEFLAGS += --no-print-directory

COMPOSE = docker compose -f compose.dev.yml
# Backend commands read the root .env when it exists (seen from backend/, it is ../.env).
# CI has no .env: its workflow sets the DB_* variables itself (ci.yml), and every other setting
# keeps its default, so `make check` runs there too.
UV_RUN = uv run $(if $(wildcard .env),--env-file ../.env)

help: ## list the commands
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "} {printf "  make %-15s %s\n", $$1, $$2}'

# --- Running the app

# The containers first (--wait: until PostgreSQL is healthy), then both dev servers side by side
# in this one terminal (-j 2). Ctrl-C stops the servers; the containers keep running (`make down`).
dev: ## start everything at http://localhost:8080
	@test -f .env || { echo "No .env yet. Run: cp .env.example .env" >&2; exit 1; }
	$(COMPOSE) up -d --wait
	$(MAKE) -j 2 dev-backend dev-frontend

# Both servers listen on 0.0.0.0, not 127.0.0.1: Caddy runs in a container, so its requests reach
# the laptop through Docker's network (host.docker.internal), not through the laptop's loopback.
# The cost: other machines on the same network could reach them too. Under WSL2 they can't by
# default, and the dev servers hold fake data only.
dev-backend: ## only Django, on port 8000 (Caddy sends /api/ and /_allauth/ here)
	cd backend && $(UV_RUN) python manage.py runserver 0.0.0.0:8000

dev-frontend: ## only Next.js, on port 3000 (Caddy sends every other path here)
	cd frontend && pnpm dev --hostname 0.0.0.0 --port 3000

# `down -v` would also delete the database volume, so it is left out on purpose.
down: ## stop and remove the containers; the database is kept
	$(COMPOSE) down

# --- Checking the code

test: ## run the backend and frontend tests
	cd backend && $(UV_RUN) pytest
	cd frontend && pnpm test

# Exactly what CI runs (ops rule). CI's four jobs (.github/workflows/ci.yml) call the four parts
# below, so the list lives only here and the laptop and CI can't drift apart. make stops at the
# first failure, so the last lines printed say what to fix.
check: check-backend check-frontend check-image check-e2e ## run everything CI runs; it must pass before any PR

# The Python half: CI's `backend` job.
# - First, `uv sync --locked`: it fails when uv.lock no longer matches pyproject.toml, instead of
#   quietly writing a new lock that nobody committed (ADR-0025). It also installs the packages,
#   which is all CI needs before the checks.
# - lint-imports checks the layer contracts in pyproject.toml (ADR-0035): an import that climbs a
#   layer fails here. Like ruff and mypy it needs no database, so it runs with them, before the
#   slower checks. --no-logo: no banner, so the last lines printed are the result.
# - makemigrations --check fails when a model changed without a migration. It runs with the test
#   settings: they install every app the dev settings do, plus the test-only probe app (CORE-2),
#   whose tables build on ShopScoped, so their migrations must follow when ShopScoped changes.
# - pytest prints a coverage report here (pyproject.toml says what is measured), so CI shows it too.
#   Among its tests, test_committed_schema_matches_the_code fails when shared/openapi.json, which the
#   app's types are made from, no longer matches the routes (UI-2): run `cd frontend && pnpm gen:api`.
# - The guard's tests: the guard refuses the costly mistakes, so a broken guard must turn this red.
# - The GitHub sync script's tests (docs/runbooks/github-setup.md). The guard and the script are
#   not backend code, but they are Python, and the backend job is the one that has Python.
check-backend: ## only the backend and the Python tools (CI's backend job)
	cd backend && uv sync --locked
	cd backend && $(UV_RUN) ruff format --check .
	cd backend && $(UV_RUN) ruff check .
	cd backend && $(UV_RUN) mypy .
	cd backend && $(UV_RUN) lint-imports --no-logo
	cd backend && $(UV_RUN) python manage.py check
	cd backend && $(UV_RUN) python manage.py makemigrations --check --dry-run --settings=config.settings.test
	cd backend && $(UV_RUN) pytest --cov
	python3 -m unittest discover -s .claude/hooks
	python3 -m unittest discover -s scripts

# The frontend half: CI's `frontend` job.
# First, `pnpm install --frozen-lockfile`, for the same reason as `uv sync --locked` above: it fails
# when pnpm-lock.yaml no longer matches package.json, instead of quietly writing a new one.
# - check:api fails when src/api/schema.d.ts no longer matches shared/openapi.json, the routes'
#   description it is made from (ADR-0025). This job has no Python, so it trusts that file; the
#   backend job's test_committed_schema_matches_the_code keeps the file true to the code. Together:
#   a serializer changed without `pnpm gen:api` turns one of the two red (UI-2).
check-frontend: ## only the frontend (CI's frontend job)
	cd frontend && pnpm install --frozen-lockfile
	cd frontend && pnpm check:api
	cd frontend && pnpm lint
	cd frontend && pnpm typecheck
	cd frontend && pnpm test
	cd frontend && pnpm build

# The backend image, which the next two parts both use. It is built from the repo root (the build
# context, backend/Dockerfile). Needs Docker, as the database already does. A target of its own, named
# by both: make runs a target once per command, so `make check` builds the image once, not twice.
# The first build takes minutes. Later ones reuse the slow install layers until a package list
# changes; a code change still re-runs `pnpm build` and collectstatic, in seconds.
# APP_VERSION is the version the image carries and /api/health/ shows (backend/Dockerfile). The same value
# goes to the build and to the check. "dev" by default; the demo's deploy passes the commit (OPS-2):
#   make check-image APP_VERSION=<commit>
APP_VERSION ?= dev
build-image: ## only build the backend image (mpc-backend:check), for the two checks below
	docker build --file backend/Dockerfile --build-arg APP_VERSION=$(APP_VERSION) --tag mpc-backend:check .

# The image part: CI's `image` job (OPS-1). scripts/smoke_image.sh starts the image and checks that it
# serves the API and the app from one address, never as root.
check-image: build-image ## only the backend image: build it, start it, check it (CI's image job)
	bash scripts/smoke_image.sh mpc-backend:check $(APP_VERSION)

# The browser tests: CI's `e2e` job (UI-6, 03 §11). A real Chromium, driven by Playwright, against the
# image and a fresh PostgreSQL, both in Docker (compose.e2e.yml); scripts/run_e2e.sh starts them, runs
# the tests and always wipes them.
# - The packages first, as in check-frontend: Playwright is one of them.
# - Then Playwright's own Chromium, the exact build its version was made for, into ~/.cache/ms-playwright/.
#   Only the headless shell (a Chromium with no window), all a test needs. Once there, this does nothing.
#   On a fresh clone or a new Playwright version, it is a download of about 100-150 MB.
# The system libraries that Chromium needs come with apt, which needs sudo: CI's job installs them in a
# step of its own, and a laptop once by hand (`cd frontend && pnpm exec playwright install-deps chromium`).
# No `sudo` in front: Playwright calls sudo for apt itself and asks for the password, and `sudo pnpm`
# would fail on most laptops, where pnpm lives in the user's own folders, which sudo's PATH leaves out.
check-e2e: build-image ## only the browser tests: the image and a fresh database, driven by Playwright (CI's e2e job)
	cd frontend && pnpm install --frozen-lockfile
	cd frontend && pnpm exec playwright install --only-shell chromium
	bash scripts/run_e2e.sh

# Lint fixes first, then formatting: a lint fix can leave code the formatter would still change,
# and `make check` would then fail its format check (ruff's own advice).
fmt: ## format the code: ruff for Python, Prettier for the frontend
	cd backend && $(UV_RUN) ruff check --fix .
	cd backend && $(UV_RUN) ruff format .
	cd frontend && pnpm format

# Once per clone. Writes small scripts into .git/hooks/ that start pre-commit, from backend's own
# packages (uv.lock): one before each commit (the files), one after its message is written (the
# `Why:` line). .pre-commit-config.yaml says what they check.
# commit.cleanup=strip (in this clone's .git/config only): git then drops `#` lines from every
# message, also from `git commit -m`, where it would otherwise keep them. The message check ignores
# those lines, so without this it could pass a message that git stores differently.
hooks: ## install the git hooks that check each commit (once per clone)
	cd backend && $(UV_RUN) pre-commit install
	git config commit.cleanup strip

# --- The database

# ADR-0012: Django can't swap its user model after the first migration, so the first `migrate`
# waits for PPL-1's custom User. The guard blocks it for scripted sessions; this check stops
# anyone who types it.
# Then the cache tables, where the pairing limits count (AUTH-5): Django makes them with its own
# command, not a migration, and leaves those already there as they are.
migrate: ## apply migrations to the dev database (refused before PPL-1) and make the cache tables
	@test -f backend/apps/people/migrations/0001_initial.py || { echo "Refused: no migrate before PPL-1 (ADR-0012)." >&2; exit 1; }
	cd backend && $(UV_RUN) python manage.py migrate
	cd backend && $(UV_RUN) python manage.py createcachetable
