# Runbook — the demo

**What:** the public demo at <https://mabatinipumba-demo.onrender.com>: the same code as the real shop, with fake data only (ADR-0029). Every merge to `main` updates it with no manual step (OPS-2).
**When:** the first setup once, after OPS-2 merges; the database every 30 days; and whenever a deploy turns red.
**Files:** `render.yaml` (the demo on Render), `backend/start-demo.sh` (how the demo starts), `.github/workflows/deploy-demo.yml` (the deploy), `scripts/smoke_demo.sh` (the check after it). Each file's header explains it.

Two words used below:
- **Blueprint:** Render's name for a `render.yaml` file in a repo. Render reads it and creates, or changes, the services and databases it describes.
- **Digest:** the fingerprint of an image's content, `sha256:…`. A tag such as `:main` can later point at another image; a digest always names the same one.

## What lives where

| What | Source of truth | Put in place by |
|---|---|---|
| The web service and the database on Render | `render.yaml` | Render, when the Blueprint is created and each time the file changes on `main` |
| The backend image | `backend/Dockerfile` | `deploy-demo.yml`, job `publish`, to `ghcr.io/jack-bita/mpc-backend` |
| The secret key, the database's details | Render | Render, by itself (`generateValue`, `fromDatabase` in `render.yaml`) |
| `DJANGO_ALLOWED_HOSTS` | Render: the service's *Environment* page | Jack, once, when the Blueprint is created |
| The deploy hook and the demo's address | GitHub: the `demo` environment | Jack, by hand, once (*First setup*, below) |

No secret is in the repo. The deploy hook is the only one GitHub holds.

## How a deploy happens

1. A pull request is squash-merged into `main`. *Deploy demo* starts in the repo's **Actions** tab.
2. **`publish`** builds the image and checks it (`make check-image`, the same as CI), with the merge's commit as its version. It pushes the image to GitHub Container Registry as `:main` and `:<commit>`, then reads its digest.
3. **`deploy`** calls Render's deploy hook with that digest. Render pulls exactly that image and starts it with `backend/start-demo.sh`, which runs `migrate` first, then gunicorn. Render keeps the old version running until the new one is up.
4. **`deploy`** then runs `scripts/smoke_demo.sh`. It asks `/api/health/` every 10 seconds until the answer carries the merge's commit (up to 15 minutes). Then it checks that `/` shows *Karibu* over HTTPS, and that `http://` is redirected to `https://`.
5. Green: the demo runs the merge. Red: see *Troubleshooting*.

One deploy runs at a time. A merge that arrives meanwhile waits for it. If a third merge arrives too, it takes the waiting one's place, and the skipped run shows as cancelled. Nothing is lost: the demo only needs the newest `main`.

## First setup (once, after OPS-2 merges)

1. **The first run is red, on purpose.** After the merge, *Deploy demo* runs: `publish` is green and the image is on GitHub; `deploy` stops at *Check that the demo is set up*, because the steps below aren't done yet.
2. **Check that the image is public**, so Render can pull it without a password: <https://github.com/users/jack-bita/packages/container/mpc-backend/settings> → **Danger Zone** shows its visibility. On the first setup (24 Oct 2026) it was public already: GitHub linked the package to this public repo when the workflow pushed it. If it says private: **Change visibility** → **Public**. The image holds only code that is public already; `backend/Dockerfile.dockerignore` keeps `.env` and `private/` out of it.
3. **A Render account**, free: <https://render.com> → **Sign up**, with GitHub or by email. Use a workspace with no other free database: Render allows one per workspace. When Render asks for access to GitHub (at sign-up, or in step 4 after an email sign-up), choose **Only select repositories** → `mpc`.
4. **The Blueprint.** Render → **New** → **Blueprint** → the `mpc` repo, branch `main`. Render reads `render.yaml` and lists `mabatinipumba-demo` (a web service) and `mabatinipumba-demo-db` (a database). It asks for one value: `DJANGO_ALLOWED_HOSTS` = `mabatinipumba-demo.onrender.com`. Apply. Render creates the database, then the service, pulls the image, runs the migrations and starts it.
   - On the first setup (24 Oct 2026) the free plan took both as written: the image-backed service and PostgreSQL 18. If Render ever refuses a line of `render.yaml`, write down its exact message, and fix the file in a small pull request before going on.
5. **Check the address** on the service's page. If Render added letters to the name (the name was taken), put that host in the service's **Environment** → `DJANGO_ALLOWED_HOSTS`, and use that address in step 7 too. Then also change the address in the README and in this runbook, in a small pull request.
6. **Copy the deploy hook:** the service → **Settings** → **Deploy Hook** → copy. It is a secret: whoever has it can start deploys. Paste it only into GitHub, in the next step.
7. **The `demo` environment on GitHub:** the repo → **Settings** → **Environments** → `demo`. The first run already created it, empty and with no rules, because GitHub creates any environment a job names. Open it and set:
   - **Deployment branches and tags:** *Selected branches and tags* → add the rule `main`. Only workflows on `main` can then read its secret.
   - **Environment secrets** → `RENDER_DEPLOY_HOOK_URL` = the hook.
   - **Environment variables** → `DEMO_URL` = `https://mabatinipumba-demo.onrender.com` (no `/` at the end).
8. **Run the deploy again:** Actions → the **newest** red *Deploy demo* run → **Re-run failed jobs**. `deploy` turns green. Only the newest: an older run would deploy its older image, and its smoke test would still pass, so the demo would quietly go back in time.

**Check:** open <https://mabatinipumba-demo.onrender.com/api/health/>; the `version` is the merge's commit. The repo page shows a deployment to `demo` with the address. The next merge to `main` updates the demo with nobody touching anything.

**Check once, after the first green deploy** (the open points of OPS-2's *Watch out*). Both passed on the first setup, 24 Oct 2026; run them again after a change to the caching or to Render's settings:

```bash
curl -s -o /dev/null -D - -H 'Accept-Encoding: br, gzip' https://mabatinipumba-demo.onrender.com/ | grep -iE 'content-encoding|cache-control'
curl -sI "https://mabatinipumba-demo.onrender.com$(curl -s https://mabatinipumba-demo.onrender.com/ | grep -o '/_next/static/[^"]*' | head -n 1)" | grep -i cache-control
```

- The first shows `content-encoding: br`: Render's proxy compresses the answers, so Django doesn't. It also shows `cache-control: max-age=0, public`: the page is checked again on every visit.
- The second shows `cache-control: max-age=315360000, public, immutable`: a file named after its content is kept for good.

## Every 30 days: the free database

Render's free PostgreSQL expires 30 days after it is created, and Render deletes it 14 days later. Render sends an email before it expires. The data is fake, so nothing needs saving.

1. Render → `mabatinipumba-demo-db` → **Settings** → **Delete Database**.
2. Render → **Blueprints** → the demo's Blueprint → **Manual Sync**. Render creates the database again from `render.yaml`, and the service's `DB_*` values follow it.
3. The service → **Manual Deploy** → **Deploy latest reference**. The start command runs every migration on the empty database.
4. Check <https://mabatinipumba-demo.onrender.com/api/health/>.

*Not yet tried:* these steps are checked the first time they are needed, about 30 days after the first setup. Correct this list then, with what Render really showed.

## What the free plan means

- **It sleeps** after 15 minutes with no visitor. The next visit wakes it, which takes about a minute. The smoke test waits for that.
- **No shell, no one-off jobs.** Nobody can run `createsuperuser` there, so the demo has no accounts at all until DATA-1's seed. That is also why the admin's login page, which has no rate limit yet, has nothing to guess.
- **No files survive a restart.** The app keeps nothing on disk; everything is in the database.
- **One instance, 512 MB.** The image's two gunicorn workers fit.

## Troubleshooting

- **`deploy` fails at *Check that the demo is set up*:** the `demo` environment, its secret or its variable is missing (*First setup*, step 7).
- **`deploy` fails at *Ask Render to deploy this image* with a 400 or 404:** the image in `imgURL` must have the same name as the one in `render.yaml` (`ghcr.io/jack-bita/mpc-backend`). Or the hook was regenerated and the secret still holds the old one.
- **The smoke test waits, then fails:** open the service's **Logs** on Render.
  - *Failed to pull image* or *unauthorized*: the package isn't public (*First setup*, step 2).
  - A migration error: the new version never started, and the old one still runs. Fix the migration in a new pull request.
  - `DisallowedHost` / `Invalid HTTP_HOST header`: `DJANGO_ALLOWED_HOSTS` doesn't hold the demo's host (step 5). A line about `localhost:10000` is Render's own port check and does no harm.
  - Database connection errors: the free database expired (*Every 30 days*).
- **The demo shows an older commit than `main`:** an older run was re-run after a newer one. Re-run the newest *Deploy demo* run, or merge again.
- **The hook leaked:** the service → **Settings** → **Deploy Hook** → regenerate, then put the new one into the `demo` environment's secret. The old one stops working at once.
