# Makefile: one short command per job, the same for Jack, the README and CI (REPO-4).
# It owns the commands, not the settings: those live in .env (copied from .env.example).
# Run `make` alone to list the commands. Recipe lines start with a real tab (.editorconfig).

# These names are jobs, not files: without this line, a file called `test` would stop `make test`.
.PHONY: help dev dev-backend dev-frontend down test check check-backend check-frontend fmt hooks migrate
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

# Exactly what CI runs (ops rule). CI's two jobs (.github/workflows/ci.yml) call the two halves
# below, so the list lives only here and the laptop and CI can't drift apart. make stops at the
# first failure, so the last lines printed say what to fix.
check: check-backend check-frontend ## run everything CI runs; it must pass before any PR

# The Python half: CI's `backend` job.
# - First, `uv sync --locked`: it fails when uv.lock no longer matches pyproject.toml, instead of
#   quietly writing a new lock that nobody committed (ADR-0025). It also installs the packages,
#   which is all CI needs before the checks.
# - makemigrations --check fails when a model changed without a migration.
# - pytest prints a coverage report here (pyproject.toml says what is measured), so CI shows it too.
# - The guard's tests: the guard refuses the costly mistakes, so a broken guard must turn this red.
# - The GitHub sync script's tests (docs/runbooks/github-setup.md). The guard and the script are
#   not backend code, but they are Python, and the backend job is the one that has Python.
check-backend: ## only the backend and the Python tools (CI's backend job)
	cd backend && uv sync --locked
	cd backend && $(UV_RUN) ruff format --check .
	cd backend && $(UV_RUN) ruff check .
	cd backend && $(UV_RUN) mypy .
	cd backend && $(UV_RUN) python manage.py check
	cd backend && $(UV_RUN) python manage.py makemigrations --check --dry-run
	cd backend && $(UV_RUN) pytest --cov
	python3 -m unittest discover -s .claude/hooks
	python3 -m unittest discover -s scripts

# The frontend half: CI's `frontend` job.
# First, `pnpm install --frozen-lockfile`, for the same reason as `uv sync --locked` above: it fails
# when pnpm-lock.yaml no longer matches package.json, instead of quietly writing a new one.
check-frontend: ## only the frontend (CI's frontend job)
	cd frontend && pnpm install --frozen-lockfile
	cd frontend && pnpm lint
	cd frontend && pnpm typecheck
	cd frontend && pnpm test
	cd frontend && pnpm build

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
migrate: ## apply migrations to the dev database (refused until PPL-1 is merged)
	@test -f backend/apps/people/migrations/0001_initial.py || { echo "Refused: no migrate before PPL-1 (ADR-0012)." >&2; exit 1; }
	cd backend && $(UV_RUN) python manage.py migrate
