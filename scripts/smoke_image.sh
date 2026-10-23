#!/usr/bin/env bash
# smoke_image.sh — proves that a backend image serves the API and the app from one address, never as root (OPS-1).
#
# It owns one check, which `make check-image` runs after building the image, and so CI's `image` job too:
#   1. the image doesn't run as root (ops rule, 03 §13);
#   2. started as a container on 127.0.0.1:8001, GET /api/health/ answers {"status":"ok"};
#   3. GET / shows "Karibu": the static app, served by WhiteNoise in the same container (03 §13);
#   4. the container is removed afterwards, whether the checks passed or not.
# A "smoke test": the quickest check that the thing starts and answers at all, before anything deeper.
#
# Usage:  bash scripts/smoke_image.sh mpc-backend:check

set -euo pipefail

image="${1:?usage: bash scripts/smoke_image.sh <image>}"
name="mpc-image-smoke"
# 8001: beside `make dev`'s ports (Django 8000, Caddy 8080, Next.js 3000), so both can run at once.
base="http://127.0.0.1:8001"

# Always remove the container: after a failed check, or Ctrl-C, too. One left running would hold port
# 8001, and the next run would then fail for the wrong reason.
trap 'docker rm --force "$name" >/dev/null 2>&1 || true' EXIT

fail() {
  echo "FAIL: $1" >&2
  # The container's own log usually says why: a missing setting, a Python error.
  docker logs "$name" >&2 2>&1 || true
  exit 1
}

# 1. `id -u` prints the number of the user the image runs as; 0 is root.
uid="$(docker run --rm --entrypoint id "$image" -u)"
[[ "$uid" != 0 ]] || fail "the image runs as root"
echo "ok: runs as uid $uid, not root"

# prod.py demands every variable, so the container gets throwaway values. No real database or secret
# is needed: the health check never touches the database (apps/core/api/views.py), and nothing here is
# signed. Checks that need the database come with OPS-2, which runs the migrations on start.
docker run --detach --name "$name" --publish 127.0.0.1:8001:8000 \
  --env DJANGO_SECRET_KEY=smoke-test-only \
  --env DJANGO_ALLOWED_HOSTS=127.0.0.1 \
  --env DB_NAME=unused --env DB_USER=unused --env DB_PASSWORD=unused --env DB_HOST=unused \
  "$image" >/dev/null

# 2. gunicorn needs a moment to start. Until it listens, a request is refused or cut off;
# --retry-all-errors retries those too: up to 30 times, one second apart.
# --fail: an error status (a 400 or a 500) fails the check too, instead of printing an error page.
echo "waiting for gunicorn; a 'Connection reset' or 'refused' line below is a retry, not a failure"
health="$(curl --silent --show-error --fail --retry 30 --retry-delay 1 --retry-all-errors "$base/api/health/")" ||
  fail "/api/health/ did not answer"
[[ "$health" == '{"status":"ok"}' ]] || fail "/api/health/ answered: $health"
echo "ok: /api/health/ answers $health"

# 3. The word is the home page's title in frontend/messages/sw.json (home.title). Change it there,
# change it here.
page="$(curl --silent --show-error --fail "$base/")" || fail "/ did not answer"
[[ "$page" == *Karibu* ]] || fail "/ doesn't show Karibu"
echo "ok: / shows Karibu"
