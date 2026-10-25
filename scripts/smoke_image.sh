#!/usr/bin/env bash
# smoke_image.sh — proves that a backend image serves the API and the app from one address, never as root (OPS-1).
#
# It owns one check, which `make check-image` runs after building the image, and so CI's `image` job too:
#   1. the image doesn't run as root (ops rule, 03 §13);
#   2. started as a container, GET /api/health/ answers "ok" with the version the image was built with;
#   3. GET / shows "Karibu": the static app, served by WhiteNoise in the same container (03 §13);
#   4. that page can't be put inside another site's frame (X-Frame-Options: DENY);
#   5. /static/ serves the admin's files, gathered by collectstatic when the image was built;
#   6. the page is checked again on every visit (max-age=0), so a deploy reaches the browser at once;
#   7. a file under /_next/static/, named after its content, is cached for good (immutable);
#   8. the app's manifest is served as a manifest, so Chrome can offer to install the app (SPIKE-1);
#   9. the service worker is served as JavaScript, checked again on every visit, with the app's files in
#      its list (SPIKE-1);
#  10. the page shows the version the image was built with, so a device's version can be checked (SPIKE-1);
#  11. the container is removed afterwards, whether the checks passed or not.
# A "smoke test": the quickest check that the thing starts and answers at all, before anything deeper.
#
# Usage:  bash scripts/smoke_image.sh mpc-backend:check [version]

set -euo pipefail

image="${1:?usage: bash scripts/smoke_image.sh <image> [version]}"
# The version the image was built with (APP_VERSION in backend/Dockerfile). The Makefile passes the same
# value to the build and to this check; "dev" when none is given, as in a plain build.
version="${2:-dev}"
# $$ is this script's process number: two runs at once (two terminals) get two containers.
name="mpc-image-smoke-$$"

# Always remove the container: after a failed check, or Ctrl-C, too, so none is left running.
trap 'docker rm --force "$name" >/dev/null 2>&1 || true' EXIT

fail() {
  echo "FAIL: $1" >&2
  # The container's own log usually says why: a missing setting, a Python error. Check 1 runs before
  # the container exists, so there may be no log to show yet.
  if docker container inspect "$name" >/dev/null 2>&1; then
    docker logs "$name" >&2 2>&1
  fi
  exit 1
}

# 1. `id -u` prints the number of the user the image runs as; 0 is root.
uid="$(docker run --rm --entrypoint id "$image" -u)"
[[ "$uid" != 0 ]] || fail "the image runs as root"
echo "ok: runs as uid $uid, not root"

# prod.py demands every variable, so the container gets throwaway values. No real database or secret
# is needed: the health check never touches the database (apps/core/api/views.py), and nothing here is
# signed. The database is checked on the demo instead: backend/start-demo.sh runs the migrations before
# gunicorn starts, so a demo that answers has reached its database (OPS-2).
# 127.0.0.1::8000 — no port number on the laptop's side, so Docker picks a free one: this can never
# clash with `make dev` (8000, 8080, 3000) or with a container someone left running.
docker run --detach --name "$name" --publish 127.0.0.1::8000 \
  --env DJANGO_SECRET_KEY=smoke-test-only \
  --env DJANGO_ALLOWED_HOSTS=127.0.0.1 \
  --env DB_NAME=unused --env DB_USER=unused --env DB_PASSWORD=unused --env DB_HOST=unused \
  "$image" >/dev/null
# `docker port` says which one it picked, as 127.0.0.1:<port>.
base="http://$(docker port "$name" 8000/tcp | head -n 1)"

# Every request gives up after 5 seconds (--max-time): one that hangs would otherwise wait for
# gunicorn's 30-second worker timeout, again on every retry, until CI's time limit cut the job
# without a FAIL line or the container's log.
# --fail: an error status (a 400 or a 500) fails the check too, instead of printing an error page.
get() {
  curl --silent --show-error --fail --max-time 5 "$@"
}

# 2. gunicorn needs a moment to start. Until it listens, a request is refused or cut off;
# --retry-all-errors retries those too: up to 30 times, one second apart.
echo "waiting for gunicorn; a 'Connection reset' or 'refused' line below is a retry, not a failure"
health="$(get --retry 30 --retry-delay 1 --retry-all-errors "$base/api/health/")" ||
  fail "/api/health/ did not answer"
# The whole answer, the version included: a build that lost APP_VERSION would answer "dev" and fail here.
[[ "$health" == "{\"status\":\"ok\",\"version\":\"$version\"}" ]] || fail "/api/health/ answered: $health"
echo "ok: /api/health/ answers $health"

# 3. The word is the home page's title in frontend/messages/sw.json (home.title). Change it there,
# change it here. --include: one answer holds the headers and the page, for this check and the next.
page="$(get --include "$base/")" || fail "/ did not answer"
[[ "$page" == *Karibu* ]] || fail "/ doesn't show Karibu"
echo "ok: / shows Karibu"

# 4. Clickjacking: another site shows our page inside an invisible frame and tricks a user into
# clicking on it. This header tells the browser to refuse any frame. ${page,,} is the answer in lower
# case, because header names may come in any case.
[[ "${page,,}" == *"x-frame-options: deny"* ]] || fail "/ can be framed by another site (no X-Frame-Options: DENY)"
echo "ok: / can't be framed (X-Frame-Options: DENY)"

# 5. A broken collectstatic or STATIC_ROOT would still pass checks 2-4, and leave the admin without
# its styles. One of its files stands for all of them.
get --output /dev/null "$base/static/admin/css/base.css" || fail "/static/ doesn't serve the admin's files"
echo "ok: /static/ serves the admin's files"

# 6. The cache rules in prod.py. The page keeps its name across deploys, so the browser must ask again
# every time; a longer max-age would keep showing the old page after a deploy.
[[ "${page,,}" == *"cache-control: max-age=0, public"* ]] || fail "/ may be kept by the browser (want Cache-Control: max-age=0)"
echo "ok: / is checked again on every visit (max-age=0)"

# 7. The first /_next/static/ file the page loads stands for all of them. [^"\] stops the match at the
# quote that ends the address (or a backslash, where the address sits inside escaped text).
asset_pattern='/_next/static/[^"\]+'
[[ "$page" =~ $asset_pattern ]] || fail "/ loads nothing from /_next/static/"
asset="${BASH_REMATCH[0]}"
# --head: only the headers, which is all this check reads.
headers="$(get --head "$base$asset")" || fail "$asset did not answer"
[[ "${headers,,}" == *"immutable"* ]] || fail "$asset is not cached for good (no immutable in Cache-Control)"
echo "ok: $asset is cached for good (immutable)"

# 8. The manifest (frontend/src/app/manifest.ts). WhiteNoise has no type for the .webmanifest ending by
# itself; prod.py's WHITENOISE_MIMETYPES gives it one. Without it the file goes out as unknown bytes.
headers="$(get --head "$base/manifest.webmanifest")" || fail "/manifest.webmanifest did not answer"
[[ "${headers,,}" == *"content-type: application/manifest+json"* ]] ||
  fail "/manifest.webmanifest is not served as application/manifest+json"
echo "ok: /manifest.webmanifest is served as a manifest"

# 9. The service worker (frontend/src/sw.ts, made into out/sw.js by `serwist build` after `next build`).
# - JavaScript: a browser refuses to install a worker served as any other type.
# - max-age=0: a new sw.js must reach the browser at once, or the update prompt never comes (03 §6.8).
# - Its list of files names index.html, so `serwist build` found the app in out/. The list sits in the
#   minified code as url:"index.html"; the bare word alone would also match Serwist's own code.
sw="$(get --include "$base/sw.js")" || fail "/sw.js did not answer"
[[ "${sw,,}" == *"content-type: text/javascript"* ]] || fail "/sw.js is not served as JavaScript"
[[ "${sw,,}" == *"cache-control: max-age=0, public"* ]] ||
  fail "/sw.js may be kept by the browser (want Cache-Control: max-age=0)"
[[ "$sw" == *'url:"index.html"'* ]] || fail "/sw.js doesn't list index.html among the files it keeps"
echo "ok: /sw.js is served as JavaScript, checked on every visit, and keeps index.html"

# 10. The version on the page (frontend/src/lib/version.ts): the commit, cut to 7 characters as GitHub
# shows it. The word is home.version in frontend/messages/sw.json: change it there, change it here. With
# the default "dev" a build that lost APP_VERSION would still pass; the demo's deploy passes the commit
# (deploy-demo.yml), so there this check tells.
short="${version:0:7}"
[[ "$page" == *"Toleo $short"* ]] || fail "/ doesn't show the version it was built with (want: Toleo $short)"
echo "ok: / shows Toleo $short"
