# Runbook — the demo

**What:** the public demo at <https://mabatinipumba-demo.onrender.com>: the same code as the real shop, with fake data only (ADR-0029). Every merge to `main` updates it with no manual step (OPS-2).
**When:** the first setup once, after OPS-2 merges; the database every 30 days; and whenever a deploy turns red.
**Files:** `render.yaml` (the demo on Render), `backend/start-demo.sh` (how the demo starts), `backend/apps/demo/services.py` (the demo seed: the demo's shop and people, DATA-1), `.github/workflows/deploy-demo.yml` (the deploy, and the nightly reset), `scripts/smoke_demo.sh` (the check after it). Each file's header explains it.

Two words used below:
- **Blueprint:** Render's name for a `render.yaml` file in a repo. Render reads it and creates, or changes, the services and databases it describes.
- **Digest:** the fingerprint of an image's content, `sha256:…`. A tag such as `:main` can later point at another image; a digest always names the same one.

## What lives where

| What | Source of truth | Put in place by |
|---|---|---|
| The web service and the database on Render | `render.yaml` | Render, when the Blueprint is created and each time the file changes on `main` |
| The backend image | `backend/Dockerfile` | `deploy-demo.yml`, job `publish`, to `ghcr.io/jack-bita/mpc-backend` |
| The secret key, the PIN pepper, the database's details | Render | Render, by itself (`generateValue`, `fromDatabase` in `render.yaml`) |
| `DJANGO_ALLOWED_HOSTS` | Render: the service's *Environment* page | Jack, once, when the Blueprint is created |
| `DEMO_SEED=yes`, the demo seed's sign (DATA-1) | `render.yaml` | Render, when it syncs the Blueprint |
| The demo's shop and people | `backend/apps/demo/services.py` | The demo's start, which runs the seed |
| The deploy hook and the demo's address | GitHub: the `demo` environment | Jack, by hand, once (*First setup*, below) |

No secret is in the repo. The deploy hook is the only one GitHub holds. Never regenerate `PIN_PEPPER` on Render: every PIN on the demo would stop working, and each person would need a new one.

**A new variable in `render.yaml`** (PPL-2 added `PIN_PEPPER`) reaches the service when Render syncs the Blueprint after the merge, usually before the new image is built. After such a merge, check that the service's **Environment** page lists it, and that the *Deploy demo* run is green.

## How a deploy happens

1. A pull request is squash-merged into `main`. *Deploy demo* starts in the repo's **Actions** tab.
2. **`publish`** builds the image and checks it (`make check-image`, the same as CI), with the merge's commit as its version. It pushes the image to GitHub Container Registry as `:main` and `:<commit>`, then reads its digest.
3. **`deploy`** calls Render's deploy hook with that digest. Render pulls exactly that image and starts it with `backend/start-demo.sh`, which runs `migrate` and `createcachetable` (the pairing limits' cache tables, AUTH-5) first, then the demo seed (`seed_demo`, below), then gunicorn. Render keeps the old version running until the new one is up.
4. **`deploy`** then runs `scripts/smoke_demo.sh`. It asks `/api/health/` every 10 seconds until the answer carries the merge's commit (up to 15 minutes). Then it checks that `/` shows *Karibu* over HTTPS, and that `http://` is redirected to `https://`.
5. Green: the demo runs the merge. Red: see *Troubleshooting*.

One deploy runs at a time. A merge that arrives meanwhile waits for it. If a third merge arrives too, it takes the waiting one's place, and the skipped run shows as cancelled. Nothing is lost: the demo only needs the newest `main`.

## The demo's people, and the nightly reset

The demo seed (`manage.py seed_demo`, DATA-1) makes one made-up shop, *Duka la Mfano*, with the sides Dawa and Vyakula. Its logins are public on purpose: visitors need them, and they open fake data only.

| Who | Logs in with | Where |
|---|---|---|
| Meneja, the manager, on every side | `meneja@example.com` and the password `jaribu-demo` | `/login/`, on a phone or a second browser |
| Asha, a seller on Dawa | PIN `2580` | a registered laptop's PIN screen |
| Baraka, a seller on Vyakula | PIN `1470` | a registered laptop's PIN screen |

None of them can open the admin: nobody the seed makes is `is_staff`.

**When it is made again.** The seed runs on every start of the demo, after the migrations:
- on a new database (the first setup, or every 30 days) it makes the shop;
- on the first start of a new day, in Arusha's time, it wipes the database and makes the shop again, so whatever visitors changed is gone;
- on a wake-up from the free plan's sleep the same day, it keeps the shop as visitors left it.

A deploy during the day keeps the day's shop too, so a merge that changes the seed shows the next morning. Every night at 00:30 in Arusha (21:30 UTC), *Deploy demo* runs by itself (`schedule` in `deploy-demo.yml`), and its start is the one that finds yesterday's shop. There is no button to reset it during the day: the free plan has no shell, and the night does it.

**Check, the morning after DATA-1 merges** (*not yet tried*): Actions → *Deploy demo* shows a green run started by `schedule`, and the demo still logs Meneja in.

**GitHub pauses a public repo's schedules after 60 days with no commit.** It sends an email. Actions → *Deploy demo* → **Enable workflow** starts the nightly runs again.

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
3. The service → **Manual Deploy** → **Deploy latest reference**. The start command runs every migration on the empty database, makes its cache tables, and the demo seed makes the demo's shop.
4. Check <https://mabatinipumba-demo.onrender.com/api/health/>.

*Not yet tried:* these steps are checked the first time they are needed, about 30 days after the first setup. Correct this list then, with what Render really showed.

## What the free plan means

- **It sleeps** after 15 minutes with no visitor. The next visit wakes it, which takes about a minute. The smoke test waits for that. A wake-up keeps the day's demo shop as visitors left it.
- **No shell, no one-off jobs.** Nobody can run `createsuperuser` or any other command there: the demo's people come from the seed at the start, and none of them can open the admin. So the admin's login page, which has no rate limit yet, has nothing to guess.
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
- **The new version stops at start with `The environment variable PIN_PEPPER is not set`** (or another variable `render.yaml` names): the deploy reached Render before the Blueprint sync added it. The old version keeps running. Render → **Blueprints** → the demo's Blueprint → **Manual Sync**; check the service's **Environment** page lists the variable; then re-run the newest *Deploy demo* run.
- **The new version stops at start with `Refused: DEMO_SEED=yes is not set`:** the deploy reached Render before the Blueprint sync added the seed's sign (the first deploy after DATA-1, or after the sign changed). The old version keeps running. The same fix as for `PIN_PEPPER`, above: **Manual Sync**, check the **Environment** page lists `DEMO_SEED`, then re-run the newest *Deploy demo* run.
- **The start stops with `Refused: the database holds a shop that isn't a demo`:** the demo's database holds a live or practice shop, which nothing on the demo can make. The seed refuses to wipe it, and the old version keeps running. Don't force anything: find out how it got there first.
- **The demo shows an older commit than `main`:** an older run was re-run after a newer one. Re-run the newest *Deploy demo* run, or merge again.
- **The hook leaked:** the service → **Settings** → **Deploy Hook** → regenerate, then put the new one into the `demo` environment's secret. The old one stops working at once.
