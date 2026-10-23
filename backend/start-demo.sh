#!/bin/sh
# start-demo.sh — how the demo starts on Render: the migrations first, then the image's usual server (OPS-2).
#
# render.yaml runs it as the service's dockerCommand, `sh start-demo.sh`. A script, not a chain written out
# in render.yaml, because Render may split that command at its spaces without honouring quotes, and a
# `sh -c "… && …"` chain would then fall apart. Two plain words can't be split wrongly.
#
# Why the migrations run here, on every start: Render's free plan has no pre-deploy command, and the demo's
# database is new every 30 days. The real server never runs this file: there the migrations are a step of
# their own, rehearsed on a scratch copy first (OPS-6), and the image's CMD starts gunicorn alone.

# Stop at the first failure. If a migration fails, gunicorn never starts, Render keeps the old version
# running, and the deploy's smoke test turns red.
set -e

python manage.py migrate --noinput

# The same server command as the image's CMD (backend/Dockerfile): change both together.
# exec: gunicorn takes this shell's place as the container's main process, so Render's stop signal reaches
# gunicorn itself, which then finishes the requests in progress before it exits.
exec gunicorn --no-control-socket config.wsgi
