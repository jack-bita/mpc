#!/usr/bin/env bash
# run_e2e.sh — runs the browser tests against the backend image and a fresh PostgreSQL, and always cleans up (UI-6).
#
# It owns one run, which `make check-e2e` starts, and so CI's e2e job too:
#   1. start compose.e2e.yml: an empty database, then the image, which runs its migrations and serves on :8090;
#   2. run Playwright (`pnpm e2e`, frontend/playwright.config.ts) against it;
#   3. on a failure, print the server's log: a test that met an error page usually finds its reason there;
#   4. stop both and delete the database, whether the tests passed or not, so the next run starts empty.
# The image must exist already: `make check-e2e` builds it first (mpc-backend:check), as check-image does.
#
# Usage:  bash scripts/run_e2e.sh

set -euo pipefail

# The repo root as a full path, wherever this is called from. Every path below starts from it, so moving
# into another folder can never send Compose looking for its file in the wrong place.
root="$(cd "$(dirname "$0")/.." && pwd)"

compose=(docker compose --file "$root/compose.e2e.yml")

finish() {
  local status=$?
  if [[ $status -ne 0 ]]; then
    echo "FAIL: the browser tests did not pass; the server's log follows." >&2
    "${compose[@]}" logs --no-color backend >&2 || true
  fi
  # --volumes: no volume is ever left behind. The database lives in memory, so nothing lasting is lost.
  # A cleanup that fails says so, rather than leave two containers running unseen; it never hides the
  # tests' own result, which is still the exit status below.
  "${compose[@]}" down --volumes >/dev/null 2>&1 ||
    echo "WARNING: the e2e containers are still there: docker compose -f compose.e2e.yml down --volumes" >&2
  exit "$status"
}
# On every way out: the tests passed, failed, or someone pressed Ctrl-C.
trap finish EXIT

# Anything an earlier run left behind (a closed terminal skips the cleanup) goes first, so the tests always
# meet an empty database: `up` would otherwise keep containers that are already running, rows and all.
"${compose[@]}" down --volumes >/dev/null 2>&1

# --wait: until both are healthy, PostgreSQL accepting connections and the image answering /api/health/
# after its migrations (compose.e2e.yml). --wait-timeout: fail after 4 minutes, rather than wait forever.
"${compose[@]}" up --detach --wait --wait-timeout 240

# In brackets, a subshell: the move into frontend/ ends with it, and the cleanup above runs from the root.
(cd "$root/frontend" && pnpm e2e)
