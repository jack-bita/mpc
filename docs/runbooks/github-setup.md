# Runbook — GitHub setup and sync

**What:** how this repo's GitHub side is set up, and how it stays in step with the build plan.
**When:** once in portion 6 (REPO-1); again at every stage review (04 §19); and whenever a CI job is added or renamed (*The required checks*, below).
**Tool:** `scripts/github_sync.py`. Its header lists every command.

## What lives where

| What | Source of truth | Put on GitHub by |
|---|---|---|
| Labels, milestones, epics, task issues, owner issues | `docs/04-build-plan.md` (§1, §4, the cards, §15) | `github_sync.py labels milestones issues owner` |
| Protection of `main` | `.github/rulesets/main.json` | `github_sync.py protect` |
| Merge settings and security features | `MERGE_SETTINGS` in the script | `github_sync.py settings` |
| The project board: fields, columns, cards | the script; the columns of 04 §4 | `github_sync.py board` |
| Issue and pull request templates | `.github/ISSUE_TEMPLATE/`, `.github/pull_request_template.md` | GitHub reads them by itself |
| Release settings | `release-please-config.json`; the current version in `.release-please-manifest.json` | `.github/workflows/release.yml`, after each merge to `main` (*Releases*, below) |
| The release app and its key | GitHub only: the app's page and the `release` environment | Jack, by hand, once (*Releases*, below) |

The plan is the source of truth, and GitHub tracks the status (04 BP12). Change a card in 04 first, then refresh its issue. Never change the issue first.

## Before the first run

```bash
gh --version                 # the GitHub CLI is installed
gh auth status               # logged in to github.com; git protocol: ssh
gh auth refresh -s project   # the board needs the "project" permission
python3 -m unittest discover -s scripts                   # the script reads 04 correctly
python3 scripts/github_sync.py plan --stage 0 --stage 1   # what it read (no GitHub needed)
```

`plan` should show 8 stages, 22 epics and 16 owner items, with 14 tasks in stage 0 and 23 in stage 1.

## First run (portion 6)

```bash
python3 scripts/github_sync.py --dry-run all --stage 0 --stage 1   # read every planned change
python3 scripts/github_sync.py all --stage 0 --stage 1             # make them
```

The steps run in this order: `settings` → `labels` → `milestones` → `issues` → `owner` → `board` → `protect`. Each change is printed as it is made. A second run changes nothing. Creating 64 issues takes a few minutes, because the script pauses after each one so GitHub doesn't think it is spam.

- **A private repo** (before the owner agrees to publish): `settings` skips secret scanning, and `protect` skips the ruleset. On GitHub Free, both need a public repo. After `gh repo edit --visibility public --accept-visibility-change-consequences`, run `python3 scripts/github_sync.py settings protect board` once more.
- **The board's columns** (Backlog → Ready → In progress → In review → Done) are set by the script on a new, empty board. If GitHub refuses, set them by hand: board → ⋯ → Settings → Status. Then run `board` again.
- **The board's layout:** views can't be made from the command line. Open the board once → *View 1* → *Layout: Board*, grouped by *Status*. GitHub's built-in board workflows move a card to *Done* when its issue closes. Check that they are on: board → ⋯ → Workflows.
- **REPO-1's issue:** close it when every box on its card is ticked: `gh issue close <number> --comment "Done in portion 6."`. `/start-task REPO-2` checks that REPO-1 is closed.

## At each stage review (04 §19)

1. Write the next stage's cards in 04 (BP2) and merge that `docs:` pull request.
2. Run `python3 scripts/github_sync.py --dry-run issues board --stage N`, then run it again without `--dry-run`.
3. To update open issues whose cards changed, add `--refresh`. It copies each changed card into its issue and adds missing labels. It never removes a label you added by hand.

## The required checks (since REPO-5)

REPO-5 added `.github/workflows/ci.yml` and, in the same pull request, the rule `required_status_checks` in `.github/rulesets/main.json`, applied with `protect`. A pull request could then merge only when both CI jobs, `backend` and `frontend`, were green.

REPO-7 added a third, `pr-title`, from `.github/workflows/pr-title.yml`: the PR title becomes the squash commit on `main` and a changelog line, so a title that breaks 04 §3.5 must block the merge too. A pull request now merges only when `backend`, `frontend` and `pr-title` are green.

- The `context` is the job's name as it appears on a pull request. **Rename a job in `ci.yml` or `pr-title.yml` only together with `main.json`**, then run `protect` again: a required check that never runs blocks every merge.
- A new required check works the same way: add the job to a workflow (`ci.yml`, or a file of its own like `pr-title.yml`), see it run on a pull request once, then add its name to `main.json` and run `protect` in that same pull request.
- `integration_id: 15368` is GitHub Actions. With it, only a CI job can turn the check green; a status with the same name sent by another app or a personal token doesn't count.

`make check` also runs `python3 -m unittest discover -s scripts` (REPO-4), so a plan the script can't read turns the `backend` check red.

## What the protection does

| Rule in `main.json` | Effect | Why |
|---|---|---|
| `pull_request`: 0 approvals, squash only | `main` changes only through a PR, merged as one squash commit | One commit per task on `main`, and release-please reads its title (BP11). It needs 0 approvals because Jack works alone, and approving your own PR would mean nothing |
| `non_fast_forward` | No force-push | History is never rewritten |
| `deletion` | `main` can't be deleted | Protects everything else |
| `required_linear_history` | No merge commits on `main` | Squash merges keep `main` a straight line |
| `required_status_checks`: `backend`, `frontend`, `pr-title` | A PR merges only when both CI jobs and the title check are green | A check that isn't required can be red and still merged (REPO-5); a bad title would land on `main` and in the changelog (REPO-7). Not *strict*: the branch needn't hold the newest `main` first, which would mean an *Update branch* click and a fresh CI run before each merge, for one person working alone |
| `bypass_actors: []` | The rules apply to admins too, Jack included | REPO-5: "a direct push to `main` is refused — your own included" |

The merge settings match: squash only; the PR title becomes the commit title and the PR body its message, so *what and why* and *What I learned* stay in `git log`; merged branches are deleted; and the *Update branch* button merges `main` in.

Merge with the title as it is. GitHub's merge box lets you edit the commit title, and an edited title lands on `main` without the `pr-title` check. `gh pr merge --squash` (04 §3.4) takes the PR title unchanged.

## Releases (since REPO-7)

release-please writes `CHANGELOG.md` and the version tags from the squash-merged PR titles (04 BP11). `.github/workflows/release.yml` runs it after every merge to `main`; its header explains the settings in `release-please-config.json`.

### How a release happens

1. A PR whose title starts with `feat`, `fix` or `perf` merges. release-please opens a release PR, `chore(main): release 0.x.y`, or updates the one already open. Its body lists the changelog lines it will add. A `chore`, `ci`, `docs`, `build`, `test` or `refactor` merge opens nothing, because users see no change.
2. CI runs on the release PR like on any other, because the release app opened it.
3. Merge it when you want the release; it can collect several features first. release-please then tags `v0.x.y` and publishes a GitHub release. `CHANGELOG.md` changes only through that PR, never by hand (ADR-0025); `.release-please-manifest.json`, which holds the last released version, is updated in the same PR.

**Versions:** `v0.x` until the first go-live, `v1.0.0` at it (04 BP11). Before 1.0, a `feat` raises the middle number (0.1.0 → 0.2.0), and a `fix` or a `perf` the last one (0.2.0 → 0.2.1).

The PR body becomes the squash commit's body, and release-please reads it too:
- **A paragraph that starts like a commit subject** (`feat: …`, `fix(core): …`), anywhere in the body, becomes an extra changelog line. To mention a subject, put it in backticks or in the middle of a sentence.
- **`Release-As: 1.0.0`** sets the next version, but only as the body's last paragraph: a blank line, then that line, at the very end. Anywhere else it is read as plain text, and the release stays 0.x. Use it once, in the PR that goes live.
- **To fix a changelog line after the merge,** edit the merged PR's body and add a block from `BEGIN_COMMIT_OVERRIDE` to `END_COMMIT_OVERRIDE` holding the right subject. The next release-please run uses it instead of the title.

### The release app (once)

release-please can't use GitHub's default token: a PR opened with it starts no workflow, so the release PR would get its required checks only if someone closed and reopened it by hand, after every update (`release.yml` explains). It uses a GitHub App instead: a small bot account of your own, allowed to touch only this repo. Its key lives on GitHub only, never on the laptop or in the repo.

1. GitHub → your picture → **Settings** → **Developer settings** → **GitHub Apps** → **New GitHub App**:
   - **GitHub App name:** `<your-username>-mpc-release` (names are unique across GitHub). It shows as the author of release PRs.
   - **Homepage URL:** the repo's address.
   - **Webhook:** untick **Active**. The app does nothing by itself; only the workflow uses it.
   - **Repository permissions:** **Contents**, **Issues** and **Pull requests**, each *Read and write*. *Metadata: Read-only* is added by itself. Nothing else.
   - **Where can this GitHub App be installed?** *Only on this account*.
   - **Create GitHub App**.
2. On the app's page, copy the **Client ID**. Then, under **Private keys**, click **Generate a private key**: a `.pem` file downloads.
3. Left menu → **Install App** → your account → **Only select repositories** → `mpc` → **Install**.
4. The repo → **Settings** → **Environments** → **New environment**, named `release`:
   - **Deployment branches and tags:** *Selected branches and tags* → add the rule `main`. Only workflows on `main` can then read this environment's secret.
   - **Environment variables** → `RELEASE_APP_CLIENT_ID` = the Client ID.
   - **Environment secrets** → `RELEASE_APP_PRIVATE_KEY` = the whole `.pem` file, from `-----BEGIN` to the last `-----`.
5. Delete the `.pem` file from your computer. GitHub holds the copy it needs, and a new key can be made at any time.

**Check:** after the next merge to `main`, Actions → *Release* is green. Before the first `feat` or `fix`, its log says it found nothing to release. Each run also shows on the repo page as a deployment to `release`: that is how GitHub marks a job that used an environment.

**If the key leaks:** on the app's page, generate a new private key, put it in the secret, then delete the old key. The old key stops working at once.

## Troubleshooting

- **"secondary rate limit"**: GitHub slows down accounts that create a lot quickly. The script waits and retries. If it still stops, wait a few minutes and run the same command again; it skips what already exists.
- **"missing scope" or "Resource not accessible" on the board**: run `gh auth refresh -s project`.
- **An issue was created twice**: the script matches issues by the ID at the start of the title (`CORE-2 · …`), so don't edit that part of a title. Close the extra one as *not planned*.
- **A task in 04 never became an issue**: run `python3 scripts/github_sync.py plan --stage N`. If the task isn't listed, its heading or table row doesn't match the shape in 04 §3.1. The tests in `scripts/test_github_sync.py` show the shapes the script reads.
