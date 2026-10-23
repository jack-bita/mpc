#!/usr/bin/env bash
# smoke_demo.sh — proves that the live demo runs a given version and serves the app over HTTPS (OPS-2).
#
# It owns the check that ends every demo deploy (.github/workflows/deploy-demo.yml):
#   1. wait until GET /api/health/ answers "ok" with the expected version, the commit just deployed.
#      Until then the answer is the old version (Render keeps it running until the new one is up), or
#      nothing at all (the free service is asleep, or waking up);
#   2. GET / shows "Karibu", over HTTPS;
#   3. a plain http:// request is redirected to https:// (Render's proxy does it; prod.py relies on it).
# Any failure exits with 1, which turns the workflow red. smoke_image.sh checks the image before it is
# pushed; this script checks the demo after it is deployed.
#
# Usage:  bash scripts/smoke_demo.sh https://mabatinipumba-demo.onrender.com <version> [seconds]
# The optional third argument is how long to wait for the version: 900 seconds (15 minutes) by default.

set -euo pipefail

usage="usage: bash scripts/smoke_demo.sh <https://address> <version> [seconds]"
base="${1:?$usage}"
version="${2:?$usage}"
wait_for="${3:-900}"
# A trailing slash would double up in the addresses below.
base="${base%/}"

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

# The demo must be checked the way a visitor reaches it, over HTTPS (04 OPS-2, Done when).
[[ "$base" == https://* ]] || fail "the address must start with https:// (got: $base)"

# --max-time 30: the first request after a quiet spell wakes the free service, which takes about a
# minute; a request that hangs longer is cut, and the loop below simply asks again.
# --fail: an error status (a 404 while the service doesn't exist yet, a 502 while it starts) counts as
# no answer, instead of an error page being read as one.
get() {
  curl --silent --show-error --fail --max-time 30 "$@"
}

# 1. Ask every 10 seconds until the new version answers, or until the time is up. SECONDS is bash's own
# count of the seconds since this script started.
expected="{\"status\":\"ok\",\"version\":\"$version\"}"
deadline=$((SECONDS + wait_for))
while true; do
  # When the request fails, keep curl's own reason (2>&1), such as "returned error: 404" while the
  # service doesn't exist or "returned error: 502" while it starts, so the log says why, not only "nothing".
  reason=""
  health="$(get "$base/api/health/" 2>&1)" || { reason="$health"; health=""; }
  [[ "$health" == "$expected" ]] && break
  # The first 120 characters are enough to see which version answers; a loading page would be long.
  answer="${health:0:120}"
  if (( SECONDS >= deadline )); then
    echo "Render's log for the service usually says why: a failed migration, a missing setting." >&2
    fail "after ${wait_for}s, /api/health/ still answers: ${answer:-nothing}${reason:+ ($reason)}"
  fi
  echo "waiting for version $version; /api/health/ answers: ${answer:-nothing yet}${reason:+ ($reason)}"
  sleep 10
done
echo "ok: /api/health/ answers $health"

# 2. The word is the home page's title in frontend/messages/sw.json (home.title), as in smoke_image.sh.
page="$(get "$base/")" || fail "/ did not answer"
[[ "$page" == *Karibu* ]] || fail "/ doesn't show Karibu"
echo "ok: / shows Karibu over HTTPS"

# 3. No --fail and no following the redirect: the answer we want is the redirect itself, and
# %{redirect_url} is the address it points to.
http_base="http://${base#https://}"
location="$(curl --silent --show-error --max-time 30 --output /dev/null --write-out '%{redirect_url}' "$http_base/")" ||
  fail "$http_base/ did not answer"
[[ "$location" == https://* ]] || fail "plain http:// is not redirected to https:// (redirect: ${location:-none})"
echo "ok: http:// is redirected to https://"
