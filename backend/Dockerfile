# backend/Dockerfile — the backend image: Django + DRF under gunicorn, with the built shop app inside (OPS-1).
#
# It owns how that image is built. One container answers everything from one address (ADR-0017):
#   /api/, /admin/, /static/  -> Django, through gunicorn
#   every other path          -> the static shop app (frontend/out/), served by WhiteNoise inside Django
# That is the demo's whole setup (03 §13, ADR-0029). On the real server Caddy serves the app itself
# (the `web` image, OPS-5), so this image's copy of it is simply never asked for there.
#
# Build it from the repo root, which is the build context, because it needs frontend/ as well:
#   docker build -f backend/Dockerfile -t mpc-backend:check .
# Dockerfile.dockerignore, beside this file, decides what the build can see: only the files it names,
# never .env or private/.
#
# Three stages; only the last one is the image we ship. The first two hold the build tools (Node, pnpm,
# uv), which stay behind: a smaller image, with fewer programs an attacker could use.
# Every image is pinned to an exact tag (ops rule); Dependabot proposes newer ones (.github/dependabot.yml).

# --- Stage 1: build the shop app into plain files, frontend/out/ (ADR-0016).
# Node 24: the version package.json's "engines" and CI's frontend job use.
FROM node:24.21.0-trixie-slim AS frontend
# Next.js would otherwise send anonymous usage data from every build.
ENV NEXT_TELEMETRY_DISABLED=1
# pnpm comes through corepack, which ships with Node 24: it reads "packageManager" in package.json, so the
# build runs the very same pnpm as the laptop and CI. No download prompt: nobody is there to answer it.
ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0
RUN corepack enable pnpm
WORKDIR /app/frontend
# The package lists first, then the slow install: Docker reuses that layer until a list changes, so a
# code change rebuilds only the steps after it. pnpm-workspace.yaml says which install scripts may run.
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
# --frozen-lockfile: fail if pnpm-lock.yaml doesn't match package.json, as `make check` does.
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm build

# --- Stage 2: install the Python packages into a virtual environment, backend/.venv.
# uv's own image, only to copy its one binary out of it. The tag must equal `required-version` in
# pyproject.toml: uv refuses to run as any other version, so a mismatch stops this build at once.
FROM ghcr.io/astral-sh/uv:0.11.33 AS uv

FROM python:3.14.7-slim-trixie AS venv
COPY --from=uv /uv /usr/local/bin/uv
# UV_PYTHON_DOWNLOADS=0: use this image's Python, never download another; the venv points at it.
# UV_COMPILE_BYTECODE=1: compile the packages to .pyc now, so the app starts faster and never needs to
# write them at run time (it couldn't: the `app` user below can't write to the code).
ENV UV_PYTHON_DOWNLOADS=0 \
    UV_COMPILE_BYTECODE=1
WORKDIR /app/backend
# The package lists first, for the same reason as in stage 1. .python-version tells uv which Python.
COPY backend/pyproject.toml backend/uv.lock backend/.python-version ./
# --locked: fail if uv.lock doesn't match pyproject.toml (ADR-0025). --no-dev: no test or lint tools.
RUN uv sync --locked --no-dev

# --- Stage 3: the image we ship.
# The same Python tag as stage 2: the venv's `python` is a link to this image's Python, so the two
# FROM lines must always match. Dependabot bumps both in one PR.
FROM python:3.14.7-slim-trixie

# PYTHONUNBUFFERED: logs come out at once, so `docker logs` shows them as they happen.
# PYTHONDONTWRITEBYTECODE: don't try to write .pyc files at run time: the `app` user couldn't, and
# they are compiled at build time instead (the packages in stage 2, our own code below).
# PATH: the venv first, so `gunicorn` and `python` are the venv's.
# DJANGO_SETTINGS_MODULE: prod settings for every command, `manage.py migrate` too (OPS-2); manage.py on
# its own would pick the dev settings. Every secret still comes from the environment at run time (prod.py).
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH=/app/backend/.venv/bin:$PATH \
    DJANGO_SETTINGS_MODULE=config.settings.prod

# The user that runs the app: never root (ops rule, 03 §13). A system user: no password, no home, no
# login shell. A fixed uid, so a server can give it files or volumes by number.
RUN groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app

WORKDIR /app/backend
# Everything below is copied as root and stays owned by root: the `app` user can read it, never change it.
# Least often changed first, so a code change reuses the layers above it.
COPY --from=venv /app/backend/.venv ./.venv
# The same place relative to backend/ as in the repo, so prod.py's WHITENOISE_ROOT is true in both.
COPY --from=frontend /app/frontend/out /app/frontend/out
COPY backend/ ./

# Gather the admin's styles and scripts into STATIC_ROOT, where WhiteNoise serves them (prod.py).
# collectstatic only reads settings: it opens no database and signs nothing. But prod.py demands every
# variable and stops Django when one is missing (on purpose), so this one command gets throwaway values.
# They exist only while this line runs; they are not part of the image's environment.
RUN DJANGO_SECRET_KEY=collectstatic-only DJANGO_ALLOWED_HOSTS=localhost \
    DB_NAME=unused DB_USER=unused DB_PASSWORD=unused DB_HOST=unused \
    python manage.py collectstatic --noinput

# Compile our own code to .pyc too: UV_COMPILE_BYTECODE in stage 2 compiled only the packages.
# Without this, every worker compiles apps/ and config/ again at each start and can't keep the result
# (the code is read-only for `app`), which slows the demo's first answer after Render wakes it (OPS-2).
RUN python -m compileall -q apps config

USER app

# gunicorn reads both by itself: PORT is the port it listens on, on every address (0.0.0.0:$PORT), and
# WEB_CONCURRENCY its number of workers. These are defaults: Render (OPS-2) and compose.prod.yml (OPS-5)
# can set their own. Two workers fit the demo's small free server; 03 §13 plans 2–4 on the real one.
ENV PORT=8000 \
    WEB_CONCURRENCY=2
EXPOSE 8000
# The exec form (a JSON list, no shell): gunicorn is process 1, so `docker stop` signals it directly
# and it finishes the requests in progress before it exits.
# --no-control-socket: gunicorn 25.1+ opens a socket through which its `gunicornc` tool can change the
# workers or stop the server. We never use it, and anything that can steer the server is one more thing
# to protect. (By default it lives in ~/.gunicorn/, and the `app` user has no home on purpose.)
CMD ["gunicorn", "--no-control-socket", "config.wsgi"]
