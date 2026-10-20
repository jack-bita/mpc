# Runbook — GitHub setup and sync

**What:** how this repo's GitHub side is set up, and how it stays in step with the build plan.
**When:** once in portion 6 (REPO-1); again at every stage review (04 §19); and when REPO-5 adds CI.
**Tool:** `scripts/github_sync.py`. Its header lists every command.

## What lives where

| What | Source of truth | Put on GitHub by |
|---|---|---|
| Labels, milestones, epics, task issues, owner issues | `docs/04-build-plan.md` (§1, §4, the cards, §15) | `github_sync.py labels milestones issues owner` |
| Protection of `main` | `.github/rulesets/main.json` | `github_sync.py protect` |
| Merge settings and security features | `MERGE_SETTINGS` in the script | `github_sync.py settings` |
| The project board: fields, columns, cards | the script; the columns of 04 §4 | `github_sync.py board` |
| Issue and pull request templates | `.github/ISSUE_TEMPLATE/`, `.github/pull_request_template.md` | GitHub reads them by itself |

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

## When REPO-5 adds CI

In the same pull request, add the CI checks to `.github/rulesets/main.json`, then run `protect`:

```json
{ "type": "required_status_checks",
  "parameters": { "strict_required_status_checks_policy": false,
                  "required_status_checks": [ { "context": "backend" }, { "context": "frontend" } ] } }
```

The `context` is the job's name as it appears on a pull request. Until then, `main` is protected but needs no checks, because a required check that never runs would block every merge.

`make check` also runs `python3 -m unittest discover -s scripts` (REPO-4), so a plan the script can't read turns the check red, and CI with it once REPO-5 runs it.

## What the protection does

| Rule in `main.json` | Effect | Why |
|---|---|---|
| `pull_request`: 0 approvals, squash only | `main` changes only through a PR, merged as one squash commit | One commit per task on `main`, and release-please reads its title (BP11). It needs 0 approvals because Jack works alone, and approving your own PR would mean nothing |
| `non_fast_forward` | No force-push | History is never rewritten |
| `deletion` | `main` can't be deleted | Protects everything else |
| `required_linear_history` | No merge commits on `main` | Squash merges keep `main` a straight line |
| `bypass_actors: []` | The rules apply to admins too, Jack included | REPO-5: "a direct push to `main` is refused — your own included" |

The merge settings match: squash only; the PR title becomes the commit title and the PR body its message, so *what and why* and *What I learned* stay in `git log`; merged branches are deleted; and the *Update branch* button merges `main` in.

## Troubleshooting

- **"secondary rate limit"**: GitHub slows down accounts that create a lot quickly. The script waits and retries. If it still stops, wait a few minutes and run the same command again; it skips what already exists.
- **"missing scope" or "Resource not accessible" on the board**: run `gh auth refresh -s project`.
- **An issue was created twice**: the script matches issues by the ID at the start of the title (`CORE-2 · …`), so don't edit that part of a title. Close the extra one as *not planned*.
- **A task in 04 never became an issue**: run `python3 scripts/github_sync.py plan --stage N`. If the task isn't listed, its heading or table row doesn't match the shape in 04 §3.1. The tests in `scripts/test_github_sync.py` show the shapes the script reads.
