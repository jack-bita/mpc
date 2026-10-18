#!/usr/bin/env python3
"""github_sync.py — the GitHub side of this repo, built from the build plan.

What it is for
--------------
`docs/04-build-plan.md` is the plan, and GitHub tracks the status (04 BP12).
This script reads the plan and creates on GitHub whatever is missing, so nothing
is typed twice and GitHub never drifts away from the plan.

    plan        print what the script reads from 04 (no GitHub needed)
    settings    squash-only merges, delete merged branches, security features
    labels      the labels of 04 §4, plus `epic`
    milestones  the milestones of 04 §4
    issues      one epic per code and one issue per task, for the stages you name
    owner       the shop and owner track (04 §15), as issues labelled `owner`
    board       the project board: its fields, its columns and every issue on it
    protect     the ruleset in .github/rulesets/main.json, applied to `main`
    all         settings, labels, milestones, issues, owner, board, protect — in that order

Running it twice is safe: it only creates what is missing (the word for this is
"idempotent"). Look first with --dry-run: it reads GitHub but changes nothing.

    python3 scripts/github_sync.py plan --stage 0 --stage 1
    python3 scripts/github_sync.py --dry-run all --stage 0 --stage 1
    python3 scripts/github_sync.py all --stage 0 --stage 1
    python3 scripts/github_sync.py issues board --stage 2 --stage 3   # at a stage review
    python3 scripts/github_sync.py issues --stage 2 --refresh         # copy changed cards into open issues

Needs Python 3.10+ and the GitHub CLI, logged in (`gh auth status`); the board
also needs the project scope (`gh auth refresh -s project`). Standard library only,
so it runs before any backend tooling is installed.
How and when to run it: docs/runbooks/github-setup.md. Tests: scripts/test_github_sync.py.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLAN_FILE = ROOT / "docs" / "04-build-plan.md"
RULESET_FILE = ROOT / ".github" / "rulesets" / "main.json"

BOARD_TITLE = "MPC build"

# GitHub has a "secondary rate limit": it refuses accounts that create a lot of
# content in a burst. A short pause after every change keeps us well under it.
PAUSE_SECONDS = 1.0

# ============================================================ what GitHub should hold

# The labels of 04 §4. Colour = hex without "#"; the description shows on hover.
LABELS: dict[str, tuple[str, str]] = {
    "size:S": ("c2e0c6", "About 1–2 hours"),
    "size:M": ("7fc8a9", "About 2–4 hours"),
    "mode:jack-led": ("f9a03f", "A short drill, then Jack writes the main code (04 BP10)"),
    "mode:claude-led": ("5b9bd5", "Claude Code writes; Jack reviews and explains it back (04 BP10)"),
    "type:feat": ("0e8a16", "New behaviour"),
    "type:fix": ("d73a4a", "Something works wrong"),
    "type:chore": ("bfbfbf", "Tooling, setup, CI, tests"),
    "type:docs": ("0075ca", "Docs and write-ups"),
    "type:spike": ("8250df", "A question answered by a quick experiment"),
    "type:ops": ("5c3d2e", "Servers, deploys, backups, monitoring, go-lives"),
    "needs-owner": ("fbca04", "Waiting for an answer from the owner or the shop (04 §15)"),
    "owner": ("b08800", "The shop and owner track (04 §15)"),
    "blocked": ("b60205", "Can't move until something else is fixed"),
    # ✚ Not in 04 §4: marks the parent issue of each epic, so the board can hide them.
    "epic": ("3e1f79", "A feature area; its tasks are its sub-issues (04 §4)"),
}

# The board's columns, left to right (04 §4). Colours are GitHub's own names.
STATUS_OPTIONS: list[tuple[str, str, str]] = [
    ("Backlog", "GRAY", "Not ready: a task it comes after, or an owner answer, is missing"),
    ("Ready", "BLUE", "Can start now (04 §3.2)"),
    ("In progress", "YELLOW", "Its branch exists; one Claude Code session"),
    ("In review", "ORANGE", "Pull request open, CI running"),
    ("Done", "GREEN", "Squash-merged; the card is ticked in 04"),
]

# One line under each milestone's title. A milestone the plan adds later gets none.
MILESTONE_NOTES = {
    "Foundation": "Stages 0–3: groundwork, foundation, offline engine, ready for real data",
    "R1b · Attendance": "Stage 4: every worker clocks in; the first month's pay",
    "R1 · Drugs": "Stages 5–6: the Drugs side replaces SmartMauzo and the paper books",
    "R1+": "Stage 7: the follow-ups in the weeks after the Drugs go-live",
    "R2 · Foods": "The Foods side",
    "R3 · Customers": "The customer side",
}

# How pull requests merge (04 BP11 and §4).
MERGE_SETTINGS = {
    "allow_squash_merge": True,   # one commit per task on main ...
    "allow_merge_commit": False,  # ... and no other way in, so main stays a straight line
    "allow_rebase_merge": False,
    # The squash commit takes the PR's conventional title — release-please reads it to
    # write the changelog — and its body, so "what and why" and "what I learned" stay in git log.
    "squash_merge_commit_title": "PR_TITLE",
    "squash_merge_commit_message": "PR_BODY",
    "delete_branch_on_merge": True,  # a merged task branch has done its job
    "allow_update_branch": True,     # the "Update branch" button merges main in: no force-push needed
    "has_wiki": False,               # the docs live in docs/, versioned with the code
}

# On GitHub Free these need a public repo.
SECRET_SCANNING = {
    "security_and_analysis": {
        "secret_scanning": {"status": "enabled"},                  # alerts for leaked keys
        "secret_scanning_push_protection": {"status": "enabled"},  # refuses the push itself
    }
}

# The type label comes from the epic first, then from the branch name's prefix.
TYPE_BY_EPIC = {"REPO": "chore", "SPIKE": "spike", "OPS": "ops", "LIVE": "ops", "FOLIO": "docs"}
TYPE_BY_BRANCH = {"feat": "feat", "fix": "fix", "docs": "docs", "spike": "spike"}  # ci/, build/, test/ → chore

# ============================================================ reading the plan

TASK_ID = re.compile(r"[A-Z]+-\d+")
CARD_HEADING = re.compile(r"^### ([A-Z]+-\d+) · (.+)$")
STAGE_HEADING = re.compile(r"^## \d+\. Stage (\d+) — ")

# The tables we read, found by their header row rather than their section number,
# so a section moving to a new number in 04 doesn't break the script.
TABLES = {
    ("Stage", "Ends with", "Milestone", "Rough hours"): "stages",  # §1
    ("Code", "Epic", "Code", "Epic"): "epics",                     # §4
    ("ID", "Task", "Size", "After", "Done when"): "tasks",         # stages 3–7
    ("ID", "What", "Who", "Needed by"): "owner",                   # §15
}


@dataclass
class Task:
    """One task: a full card (### heading) or, for far stages, a one-line table row (04 BP2)."""

    id: str
    title: str
    stage: int
    body: str                    # the card under its heading, as Markdown
    size: str | None = None      # "S" or "M"
    mode: str | None = None      # "Jack-led" or "Claude-led"
    branch: str | None = None
    needs: list[str] = field(default_factory=list)  # owner answers it waits for (OWN-…)
    is_card: bool = True

    @property
    def epic(self) -> str:
        return self.id.split("-")[0]

    @property
    def type(self) -> str:
        if self.epic in TYPE_BY_EPIC:
            return TYPE_BY_EPIC[self.epic]
        if self.branch:
            return TYPE_BY_BRANCH.get(self.branch.split("/")[0], "chore")
        return "feat"

    @property
    def labels(self) -> list[str]:
        labels = [f"type:{self.type}"]
        if self.size:
            labels.append(f"size:{self.size}")
        if self.mode:
            labels.append(f"mode:{self.mode.lower()}")
        if self.needs:
            labels.append("needs-owner")
        return labels


@dataclass
class OwnerItem:
    """One row of the shop and owner track (04 §15): something only Jack, the owner or the shop can do."""

    id: str
    what: str
    who: str
    needed_by: str


class Plan:
    """Everything this script needs from docs/04-build-plan.md, read once, line by line."""

    def __init__(self, text: str) -> None:
        self.stage_names: dict[int, str] = {}      # 0 → "0 Groundwork"       (§1 table)
        self.stage_milestone: dict[int, str] = {}  # 0 → "Foundation"         (§1 table)
        self.milestones: list[str] = []            # in order                 (§4)
        self.epics: dict[str, str] = {}            # "CORE" → "Base models, …" (§4 table)
        self.tasks: dict[str, Task] = {}           # in plan order
        self.owner_items: dict[str, OwnerItem] = {}
        self.duplicates: list[str] = []            # an ID seen twice is a mistake in 04
        self._read(text.splitlines())

    def tasks_in(self, stages: list[int]) -> list[Task]:
        return [task for task in self.tasks.values() if task.stage in stages]

    def milestone_of(self, stage: int) -> str:
        return self.stage_milestone[stage]

    def stage_of(self, item: OwnerItem, seen: tuple[str, ...] = ()) -> int:
        """The stage an owner item is needed by: the stage of the first task it names, or of the
        owner item it waits on (OWN-15 → OWN-3 → OPS-5). "Before each go-live" means: now."""
        for ref in TASK_ID.findall(item.needed_by):
            if ref in self.tasks:
                return self.tasks[ref].stage
            if ref in self.owner_items and ref not in seen:  # `seen` stops a loop A → B → A
                return self.stage_of(self.owner_items[ref], (*seen, item.id))
        return min(self.stage_names)

    # -------------------------------------------------------------- the reader
    def _read(self, lines: list[str]) -> None:
        stage: int | None = None        # the stage section we are in ("## 6. Stage 1 — …"), if any
        table: str | None = None        # the known table we are in (see TABLES), if any
        card: list[str] | None = None   # the lines of the card being read
        in_fence = False                # inside a ``` block: a heading there is only an example (04 §3.1)

        for line in lines:
            if line.lstrip().startswith("```"):
                in_fence = not in_fence
            if not in_fence and line.startswith("## "):
                self._finish_card(card, stage)
                card, table = None, None
                match = STAGE_HEADING.match(line)
                stage = int(match.group(1)) if match else None
                continue
            if not in_fence and line.startswith("### "):
                self._finish_card(card, stage)
                card, table = None, None
                if stage is not None and CARD_HEADING.match(line):
                    card = [line]
                continue
            if card is not None:  # a card runs until the next heading
                card.append(line)
                continue
            if in_fence:
                continue
            if "**Milestones:**" in line:
                self.milestones = re.findall(r"`([^`]+)`", line)
                continue
            if not line.startswith("|"):
                table = None
                continue
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if all(set(cell) <= set("-: ") for cell in cells):
                continue  # the |---|---| line under a header
            if tuple(cells) in TABLES:
                table = TABLES[tuple(cells)]
            elif table == "stages":
                self._read_stage_row(cells)
            elif table == "epics":
                self._read_epic_row(cells)
            elif table == "tasks" and stage is not None:
                self._read_task_row(cells, stage)
            elif table == "owner":
                self._read_owner_row(cells)
        self._finish_card(card, stage)

    def _finish_card(self, card: list[str] | None, stage: int | None) -> None:
        if card is None or stage is None:
            return
        heading = CARD_HEADING.match(card[0])
        assert heading is not None  # only matching headings start a card
        body = card[1:]
        # The line under the heading: `M` · Jack-led · after SHOP-1 · needs OWN-2 · branch `feat/…`
        # REPO-1 has none: it is done in chat, not in a Claude Code session.
        meta = body[0] if body and body[0].startswith("`") else ""
        parts = [part.strip() for part in meta.split(" · ")] if meta else []
        size = parts[0].strip("`") if parts and parts[0].strip("`") in ("S", "M") else None
        mode = next((part for part in parts if part in ("Jack-led", "Claude-led")), None)
        needs = [ref for part in parts if part.startswith("needs ") for ref in TASK_ID.findall(part)]
        branch = next((part.split("`")[1] for part in parts if part.startswith("branch `")), None)
        self._add(Task(heading.group(1), heading.group(2).strip(), stage, "\n".join(body).strip(),
                       size, mode, branch, needs, is_card=True))

    def _read_task_row(self, cells: list[str], stage: int) -> None:
        # | OPS-4 | Production server … *(Jack-led)* | M | OPS-1 | SSH keys only, … |
        if len(cells) < 5 or not TASK_ID.fullmatch(cells[0]):
            return
        task_id, title, size, after = cells[:4]
        done_when = " | ".join(cells[4:])
        jack_led = "(Jack-led)" in title
        title = re.sub(r"\s*\*\(Jack-led\)\*", "", title).strip()
        size_or_none = size if size in ("S", "M") else None  # go-lives have "—": not a coding task
        mode = "Jack-led" if jack_led else ("Claude-led" if size_or_none else None)
        meta = " · ".join(part for part in (
            f"`{size_or_none}`" if size_or_none else "",
            mode or "",
            f"after {after}" if after not in ("", "—") else "",
        ) if part)
        body = f"{meta}\n**Done when:** {done_when}".strip()
        self._add(Task(task_id, title, stage, body, size_or_none, mode, None, [], is_card=False))

    def _read_stage_row(self, cells: list[str]) -> None:
        # | 0 Groundwork | CI green, … | Foundation | 30–45 |
        match = re.match(r"^(\d+) (.+)$", cells[0])
        if match and len(cells) >= 3:
            number = int(match.group(1))
            self.stage_names[number] = cells[0]
            self.stage_milestone[number] = cells[2]

    def _read_epic_row(self, cells: list[str]) -> None:
        # | `REPO` | Repository, tooling, CI | `ATT` | Attendance |  — two epics per row
        for code_cell, name in zip(cells[0::2], cells[1::2]):
            match = re.fullmatch(r"`([A-Z]+)`", code_cell)
            if match:
                self.epics[match.group(1)] = name

    def _read_owner_row(self, cells: list[str]) -> None:
        # | OWN-9 | The product sheet filled in, … **start in stage 1** | Jack + siblings | DATA-4 |
        if len(cells) >= 4 and re.fullmatch(r"OWN-\d+", cells[0]):
            self.owner_items[cells[0]] = OwnerItem(cells[0], cells[1].replace("**", ""), cells[2], cells[3])

    def _add(self, task: Task) -> None:
        if task.id in self.tasks:
            self.duplicates.append(task.id)
        else:
            self.tasks[task.id] = task


# ============================================================ issue bodies

def task_body(task: Task) -> str:
    refresh = f"`python3 scripts/github_sync.py issues --stage {task.stage} --refresh`"
    note = (f"The card in `docs/04-build-plan.md` (stage {task.stage}) is the source of truth: "
            f"change the card, then run {refresh}.")
    if not task.is_card:
        note = ("One line in the plan so far — its full card is written at the review that ends "
                "the stage before (04 BP2). " + note)
    return f"{task.body}\n\n---\n*{note}*\n"


def epic_body(code: str, name: str) -> str:
    return (f"**Epic `{code}`:** {name}.\n\n"
            f"Its tasks are the sub-issues below (IDs `{code}-…`), and its progress shows here as they close. "
            "The cards are in `docs/04-build-plan.md`.\n")


def owner_body(item: OwnerItem) -> str:
    return (f"**Who:** {item.who} · **Needed by:** {item.needed_by}\n\n"
            f"{item.what}\n\n---\n"
            "*From the shop and owner track, `docs/04-build-plan.md` §15. When the answer is in, write it "
            "here and close this issue. This repo is public: real names, phone numbers, prices and amounts "
            "go in `private/`, never here.*\n")


# ============================================================ talking to GitHub

class GitHubError(RuntimeError):
    """A gh command failed; the message holds GitHub's answer."""


def run_gh(args: list[str], payload: object = None) -> str:
    """Run one `gh` command and return what it printed. A JSON payload goes in on stdin
    (`--input -`), so no value is ever mangled by shell quoting."""
    for attempt in (1, 2, 3):
        try:
            result = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=120,
                                    input=None if payload is None else json.dumps(payload))
        except FileNotFoundError:
            raise SystemExit("The GitHub CLI (gh) is not installed — see docs/runbooks/github-setup.md.")
        if result.returncode == 0:
            return result.stdout
        message = (result.stderr or result.stdout).strip()
        if "rate limit" in message.lower() and attempt < 3:
            wait = 60 * attempt
            print(f"    GitHub asks us to slow down; waiting {wait} s, then trying again …")
            time.sleep(wait)
            continue
        raise GitHubError(f"`gh {' '.join(args[:4])} …` failed:\n{message}")
    raise AssertionError("unreachable")


@dataclass
class Issue:
    key: str               # what comes before " · " in the title: "CORE-2", "CORE" or "OWN-3"
    number: int | None     # None only in a dry run, for an issue that would be created
    id: int | None         # the REST id; linking a sub-issue needs it, not the number
    title: str
    url: str
    state: str
    body: str
    labels: list[str]

    @classmethod
    def from_api(cls, data: dict) -> Issue:
        return cls(key=data["title"].split(" · ", 1)[0].strip(), number=data["number"], id=data["id"],
                   title=data["title"], url=data["html_url"], state=data["state"], body=data.get("body") or "",
                   labels=[label["name"] for label in data.get("labels", [])])


class GitHub:
    """One repo on GitHub. Reads always run; changes only print in a dry run."""

    def __init__(self, repo: str, dry_run: bool) -> None:
        self.repo = repo
        self.dry_run = dry_run
        self.changes = 0

    def read_json(self, *args: str) -> object:
        out = run_gh(list(args))
        return json.loads(out) if out.strip() else None

    def api_list(self, path: str) -> list[dict]:
        """Every page of a REST list, 100 at a time."""
        items: list[dict] = []
        joiner = "&" if "?" in path else "?"
        page = 1
        while True:
            batch = self.read_json("api", f"{path}{joiner}per_page=100&page={page}") or []
            assert isinstance(batch, list)
            items.extend(batch)
            if len(batch) < 100:
                return items
            page += 1

    def change(self, what: str, args: list[str], payload: object = None, say: bool = True) -> str | None:
        """Make one change — or, in a dry run, only say what it would be."""
        self.changes += 1
        if self.dry_run:
            if say:
                print(f"  would {what}")
            return None
        if say:
            print(f"  {what}")
        out = run_gh(args, payload)
        time.sleep(PAUSE_SECONDS)
        return out

    def api_change(self, what: str, method: str, path: str, payload: object = None,
                   say: bool = True) -> dict | None:
        args = ["api", "-X", method, path, *(["--input", "-"] if payload is not None else [])]
        out = self.change(what, args, payload, say)
        return json.loads(out) if out and out.strip() else None


def optional(what: str, step: Callable[[], object]) -> None:
    """Run a step that may not exist for this account; report a refusal instead of stopping."""
    try:
        step()
    except GitHubError as error:
        print(f"  ! skipped {what}: {str(error).splitlines()[-1]}")


@dataclass
class Context:
    gh: GitHub
    plan: Plan
    owner: str
    public: bool
    stages: list[int]
    refresh: bool


# ============================================================ the steps

def step_settings(ctx: Context) -> None:
    gh = ctx.gh
    current = gh.read_json("api", f"repos/{gh.repo}") or {}
    assert isinstance(current, dict)
    wanted = {key: value for key, value in MERGE_SETTINGS.items() if current.get(key) != value}
    squash_pair = ("squash_merge_commit_title", "squash_merge_commit_message")
    if any(key in wanted for key in squash_pair):  # GitHub accepts the commit message only with its title
        wanted.update({key: MERGE_SETTINGS[key] for key in squash_pair})
    if wanted:
        gh.api_change("set merges: squash only, PR title as the commit, delete merged branches "
                      f"({len(wanted)} settings)", "PATCH", f"repos/{gh.repo}", wanted)

    # Dependabot alerts warn when a dependency has a known hole. Turning on also enables
    # its security fixes: small PRs that bump just that dependency.
    if not alerts_on(gh):
        optional("Dependabot alerts", lambda: gh.api_change(
            "turn on Dependabot alerts", "PUT", f"repos/{gh.repo}/vulnerability-alerts"))
    fixes = read_optional(gh, f"repos/{gh.repo}/automated-security-fixes")
    if not fixes.get("enabled"):
        optional("Dependabot security updates", lambda: gh.api_change(
            "turn on Dependabot security updates", "PUT", f"repos/{gh.repo}/automated-security-fixes"))

    if not ctx.public:
        print("  skip secret scanning and private vulnerability reporting: on GitHub Free they need a "
              "public repo. Run `settings` again right after publishing.")
        return
    security = current.get("security_and_analysis") or {}
    if any((security.get(key) or {}).get("status") != "enabled"
           for key in SECRET_SCANNING["security_and_analysis"]):
        optional("secret scanning", lambda: gh.api_change(
            "turn on secret scanning and push protection", "PATCH", f"repos/{gh.repo}", SECRET_SCANNING))
    if not read_optional(gh, f"repos/{gh.repo}/private-vulnerability-reporting").get("enabled"):
        optional("private vulnerability reporting", lambda: gh.api_change(
            "turn on private vulnerability reporting", "PUT", f"repos/{gh.repo}/private-vulnerability-reporting"))


def alerts_on(gh: GitHub) -> bool:
    """GitHub answers 204 (on) or 404 (off); gh turns a 404 into an error."""
    try:
        run_gh(["api", f"repos/{gh.repo}/vulnerability-alerts"])
        return True
    except GitHubError:
        return False


def read_optional(gh: GitHub, path: str) -> dict:
    try:
        data = gh.read_json("api", path)
        return data if isinstance(data, dict) else {}
    except GitHubError:
        return {}


def step_labels(ctx: Context) -> None:
    gh = ctx.gh
    existing = {label["name"]: label for label in gh.api_list(f"repos/{gh.repo}/labels")}
    for name, (color, description) in LABELS.items():
        old = existing.get(name)
        if old and old["color"].lower() == color and (old.get("description") or "") == description:
            continue
        # --force updates a label that exists, so this one command both creates and fixes.
        gh.change(f"{'update' if old else 'create'} label {name}",
                  ["label", "create", name, "--repo", gh.repo, "--color", color,
                   "--description", description, "--force"])


def step_milestones(ctx: Context) -> None:
    gh = ctx.gh
    existing = {m["title"] for m in gh.api_list(f"repos/{gh.repo}/milestones?state=all")}
    for title in ctx.plan.milestones:
        if title not in existing:
            gh.api_change(f"create milestone {title}", "POST", f"repos/{gh.repo}/milestones",
                          {"title": title, "description": MILESTONE_NOTES.get(title, "")})


def list_issues(gh: GitHub) -> dict[str, Issue]:
    """Every issue (open and closed), by the ID at the start of its title. Oldest first,
    so if an ID was ever used twice, the first issue wins."""
    issues: dict[str, Issue] = {}
    for data in gh.api_list(f"repos/{gh.repo}/issues?state=all&sort=created&direction=asc"):
        if "pull_request" in data:  # the issues API lists pull requests too
            continue
        issue = Issue.from_api(data)
        issues.setdefault(issue.key, issue)
    return issues


def milestone_numbers(gh: GitHub) -> dict[str, int]:
    return {m["title"]: m["number"] for m in gh.api_list(f"repos/{gh.repo}/milestones?state=all")}


def require_labels(gh: GitHub, needed: set[str]) -> None:
    """Issues must only use our labels. Without this check, a missing label would be made
    by GitHub on the fly — grey, with no description."""
    if gh.dry_run:
        return
    missing = needed - {label["name"] for label in gh.api_list(f"repos/{gh.repo}/labels")}
    if missing:
        raise SystemExit(f"These labels don't exist yet: {', '.join(sorted(missing))}. Run `labels` first.")


def ensure_issue(ctx: Context, existing: dict[str, Issue], milestones: dict[str, int], key: str,
                 title: str, body: str, labels: list[str], milestone: str | None,
                 note: str = "") -> tuple[Issue, bool]:
    """Find the issue whose title starts with `key`, or create it. Returns (issue, created)."""
    gh = ctx.gh
    found = existing.get(key)
    if found:
        if ctx.refresh and found.state == "open":
            if found.body.replace("\r\n", "\n").strip() != body.strip():
                gh.api_change(f"refresh #{found.number} {found.title}", "PATCH",
                              f"repos/{gh.repo}/issues/{found.number}", {"body": body})
            missing = [label for label in labels if label not in found.labels]
            if missing:  # only adds: a label set by hand (blocked, needs-owner …) is never removed
                gh.api_change(f"add {', '.join(missing)} to #{found.number}", "POST",
                              f"repos/{gh.repo}/issues/{found.number}/labels", {"labels": missing})
        return found, False

    payload: dict[str, object] = {"title": title, "body": body, "labels": labels}
    if milestone:
        if milestone in milestones:
            payload["milestone"] = milestones[milestone]
        elif not gh.dry_run:
            raise SystemExit(f"The milestone “{milestone}” doesn't exist yet. Run `milestones` first.")
    where = f"[{milestone}] " if milestone else ""
    created = gh.api_change(f"create {title}  {where}{' '.join(labels)}{note}", "POST",
                            f"repos/{gh.repo}/issues", payload)
    issue = Issue.from_api(created) if created else Issue(key, None, None, title, "", "open", body, labels)
    existing[key] = issue
    return issue, True


def link_sub_issue(gh: GitHub, epic: Issue, task: Issue, known: dict[int, set[int]], say: bool) -> None:
    """Put a task under its epic (GitHub "sub-issues"), so the epic shows its progress."""
    if epic.number is None or task.id is None:
        gh.changes += 1  # a dry run: one of the two doesn't exist yet, so nothing to look up
        return
    if epic.number not in known:
        known[epic.number] = {sub["id"] for sub in gh.api_list(f"repos/{gh.repo}/issues/{epic.number}/sub_issues")}
    if task.id in known[epic.number]:
        return
    try:
        gh.api_change(f"put {task.key} under epic {epic.key}", "POST",
                      f"repos/{gh.repo}/issues/{epic.number}/sub_issues", {"sub_issue_id": task.id}, say=say)
        known[epic.number].add(task.id)
    except GitHubError as error:  # e.g. it already sits under another epic: report, don't stop
        print(f"  ! couldn't put {task.key} under {epic.key}: {str(error).splitlines()[-1]}")


def step_issues(ctx: Context) -> None:
    gh, plan = ctx.gh, ctx.plan
    tasks = plan.tasks_in(ctx.stages)
    if not tasks:
        raise SystemExit(f"No tasks in stage(s) {ctx.stages} of the plan.")
    require_labels(gh, {"epic", *(label for task in tasks for label in task.labels)})
    existing = list_issues(gh)
    milestones = milestone_numbers(gh)

    # Epics first, only for the codes these stages use (BP12: no empty parents).
    epics: dict[str, Issue] = {}
    for code in dict.fromkeys(task.epic for task in tasks):  # first-seen order, no repeats
        name = plan.epics.get(code, "add this code to the epics table in 04 §4")
        epics[code], _ = ensure_issue(ctx, existing, milestones, code, f"{code} · {name}",
                                      epic_body(code, name), ["epic"], None)

    known_subs: dict[int, set[int]] = {}
    for task in tasks:
        issue, created = ensure_issue(ctx, existing, milestones, task.id, f"{task.id} · {task.title}",
                                      task_body(task), task.labels, plan.milestone_of(task.stage),
                                      note=f", under {task.epic}")
        link_sub_issue(gh, epics[task.epic], issue, known_subs, say=not created)


def step_owner(ctx: Context) -> None:
    gh, plan = ctx.gh, ctx.plan
    require_labels(gh, {"owner"})
    existing = list_issues(gh)
    milestones = milestone_numbers(gh)
    for item in plan.owner_items.values():
        ensure_issue(ctx, existing, milestones, item.id, f"{item.id} · {item.what}", owner_body(item),
                     ["owner"], plan.milestone_of(plan.stage_of(item)))


def step_protect(ctx: Context) -> None:
    gh = ctx.gh
    if not ctx.public:
        print("  skip: on GitHub Free, rulesets need a public repo. Run `protect` again right after publishing.")
        return
    ruleset = json.loads(RULESET_FILE.read_text(encoding="utf-8"))
    existing = gh.read_json("api", f"repos/{gh.repo}/rulesets?includes_parents=false") or []
    assert isinstance(existing, list)
    match = next((r for r in existing if r.get("name") == ruleset["name"]), None)
    if match is None:
        gh.api_change(f"create the ruleset “{ruleset['name']}”: main changes only through squash-merged PRs",
                      "POST", f"repos/{gh.repo}/rulesets", ruleset)
        return
    current = gh.read_json("api", f"repos/{gh.repo}/rulesets/{match['id']}") or {}
    assert isinstance(current, dict)
    if ruleset_matches(current, ruleset):
        print(f"  the ruleset “{ruleset['name']}” already matches {RULESET_FILE.relative_to(ROOT)}")
        return
    gh.api_change(f"update the ruleset “{ruleset['name']}” from {RULESET_FILE.relative_to(ROOT)}",
                  "PUT", f"repos/{gh.repo}/rulesets/{match['id']}", ruleset)


def ruleset_matches(current: dict, wanted: dict) -> bool:
    """True when GitHub's ruleset already says what the file says. GitHub adds default
    values to what it stores, so only the keys the file sets are compared."""
    if current.get("enforcement") != wanted["enforcement"]:
        return False
    if (current.get("bypass_actors") or []) != wanted["bypass_actors"]:
        return False
    if current.get("conditions", {}).get("ref_name") != wanted["conditions"]["ref_name"]:
        return False
    have = {rule["type"]: rule.get("parameters", {}) for rule in current.get("rules", [])}
    if set(have) != {rule["type"] for rule in wanted["rules"]}:
        return False
    return all(have[rule["type"]].get(key) == value
               for rule in wanted["rules"] for key, value in rule.get("parameters", {}).items())


# ------------------------------------------------------------------ the board

def step_board(ctx: Context) -> None:
    gh, plan, owner = ctx.gh, ctx.plan, ctx.owner
    try:
        listing = gh.read_json("project", "list", "--owner", owner, "--format", "json", "--limit", "100") or {}
    except GitHubError as error:
        print(f"  ! can't read projects: {str(error).splitlines()[-1]}\n"
              "    The board needs the project scope: gh auth refresh -s project")
        return
    assert isinstance(listing, dict)
    project = next((p for p in listing.get("projects", []) if p.get("title") == BOARD_TITLE), None)
    if project is None:
        out = gh.change(f"create the project board “{BOARD_TITLE}”",
                        ["project", "create", "--owner", owner, "--title", BOARD_TITLE, "--format", "json"])
        if out is None:
            print("  would then add the fields Stage, Size, Mode and Hours, set the columns, and add every issue")
            return
        project = json.loads(out)
        gh.change(f"link the board to {gh.repo}",
                  ["project", "link", str(project["number"]), "--owner", owner, "--repo", gh.repo])
    number, project_id = str(project["number"]), project["id"]

    fields = board_fields(gh, number, owner)
    for name, kind, options in board_field_specs(plan):
        if name not in fields:
            args = ["project", "field-create", number, "--owner", owner, "--name", name, "--data-type", kind]
            if options:
                args += ["--single-select-options", ",".join(options)]
            gh.change(f"add the field {name}", args)
    items = board_items(gh, number, owner)
    if not set_columns(gh, fields, items):
        return
    if not gh.dry_run:
        fields = board_fields(gh, number, owner)  # re-read: the new fields and options have IDs now

    on_board = {(item.get("content") or {}).get("url") for item in items}
    for issue in sorted(list_issues(gh).values(), key=lambda i: i.number or 0):
        values = board_values(issue, plan)
        if values is None or issue.url in on_board:
            continue
        out = gh.change(f"add #{issue.number} {issue.key} ({' · '.join(values.values())})",
                        ["project", "item-add", number, "--owner", owner, "--url", issue.url, "--format", "json"])
        if out is None:
            continue
        item_id = json.loads(out)["id"]
        for field_name, value in values.items():
            set_option(gh, project_id, item_id, fields, field_name, value)

    if ctx.public and not project.get("public"):
        gh.change("make the board public, like the repo",
                  ["project", "edit", number, "--owner", owner, "--visibility", "PUBLIC"])
    print("  The board's layout is set by hand once: open it → View 1 → Layout: Board (group by Status).")


def board_field_specs(plan: Plan) -> list[tuple[str, str, list[str]]]:
    stages = [plan.stage_names[n] for n in sorted(plan.stage_names)]
    # gh takes the options as one comma-separated string, so a comma inside a name would split it.
    stages = [name.replace(",", ";") for name in stages]
    return [
        ("Stage", "SINGLE_SELECT", stages),
        ("Size", "SINGLE_SELECT", ["S", "M"]),
        ("Mode", "SINGLE_SELECT", ["Jack-led", "Claude-led"]),
        ("Hours", "NUMBER", []),  # filled in by hand when the PR merges (04 §19)
    ]


def board_fields(gh: GitHub, number: str, owner: str) -> dict[str, dict]:
    data = gh.read_json("project", "field-list", number, "--owner", owner, "--format", "json", "--limit", "100")
    return {f["name"]: f for f in data.get("fields", [])} if isinstance(data, dict) else {}


def board_items(gh: GitHub, number: str, owner: str) -> list[dict]:
    data = gh.read_json("project", "item-list", number, "--owner", owner, "--format", "json", "--limit", "1000")
    return data.get("items", []) if isinstance(data, dict) else []


def set_columns(gh: GitHub, fields: dict[str, dict], items: list[dict]) -> bool:
    """Make the Status field hold exactly the five columns of 04 §4. GitHub replaces the whole
    list at once, which would wipe the column of every card already on the board — so the
    script only does it on an empty board, and asks for two clicks otherwise."""
    status = fields.get("Status")
    want = [name for name, _, _ in STATUS_OPTIONS]
    have = [option["name"] for option in (status or {}).get("options", [])]
    if have == want:
        return True
    by_hand = ("    Set the columns by hand, then run `board` again: open the board → ⋯ → Settings → Status,\n"
               "    and make the options: " + ", ".join(want) + ".")
    if status is None or items:
        print("  ! the board's Status columns aren't the five of 04 §4, and the board isn't empty.\n" + by_hand)
        return False
    mutation = ("mutation($input: UpdateProjectV2FieldInput!) { updateProjectV2Field(input: $input) "
                "{ projectV2Field { ... on ProjectV2SingleSelectField { id } } } }")
    options = [{"name": name, "color": color, "description": text} for name, color, text in STATUS_OPTIONS]
    payload = {"query": mutation, "variables": {"input": {"fieldId": status["id"], "singleSelectOptions": options}}}
    try:
        gh.change("set the columns: " + " → ".join(want), ["api", "graphql", "--input", "-"], payload)
    except GitHubError as error:
        print(f"  ! GitHub refused to change the columns: {str(error).splitlines()[-1]}\n" + by_hand)
        return False
    return True


def board_values(issue: Issue, plan: Plan) -> dict[str, str] | None:
    """The board fields for one of our issues; None for any other issue."""
    values = {"Status": "Done" if issue.state == "closed" else "Backlog"}
    task = plan.tasks.get(issue.key)
    if task:
        values["Stage"] = plan.stage_names[task.stage].replace(",", ";")
        if task.size:
            values["Size"] = task.size
        if task.mode:
            values["Mode"] = task.mode
        return values
    item = plan.owner_items.get(issue.key)
    if item:
        values["Stage"] = plan.stage_names[plan.stage_of(item)].replace(",", ";")
        return values
    return values if issue.key in plan.epics else None


def set_option(gh: GitHub, project_id: str, item_id: str, fields: dict[str, dict], name: str, value: str) -> None:
    board_field = fields.get(name) or {}
    option = next((o for o in board_field.get("options", []) if o["name"] == value), None)
    if option is None:
        print(f"    ! the field {name} has no option “{value}”; set it by hand")
        return
    gh.change(f"{name} = {value}", ["project", "item-edit", "--id", item_id, "--project-id", project_id,
                                    "--field-id", board_field["id"], "--single-select-option-id", option["id"]],
              say=False)


# ============================================================ the command line

STEPS = {
    "settings": step_settings,
    "labels": step_labels,
    "milestones": step_milestones,
    "issues": step_issues,
    "owner": step_owner,
    "board": step_board,
    "protect": step_protect,
}


def print_plan(plan: Plan, stages: list[int]) -> None:
    print(f"The plan as this script reads it ({PLAN_FILE.relative_to(ROOT)}):\n")
    print(f"  milestones   {' · '.join(plan.milestones)}")
    print(f"  epics        {len(plan.epics)}: {', '.join(plan.epics)}")
    for number in sorted(plan.stage_names):
        tasks = plan.tasks_in([number])
        cards = sum(task.is_card for task in tasks)
        print(f"  stage {plan.stage_names[number]:<27} → {plan.milestone_of(number):<17}"
              f"{len(tasks):>3} tasks, {cards} with full cards")
    print(f"  owner track  {len(plan.owner_items)} items")
    if plan.duplicates:
        print(f"  ! these IDs appear twice in the plan: {', '.join(plan.duplicates)}")
    for number in stages:
        print(f"\nStage {plan.stage_names[number]}: the issues `issues --stage {number}` makes")
        for task in plan.tasks_in([number]):
            print(f"  {task.id:<9} {task.title[:50]:<50}  {' '.join(task.labels)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="github_sync.py", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("commands", nargs="+", metavar="command", choices=["plan", "all", *STEPS],
                        help="plan, all, or any of: " + ", ".join(STEPS))
    parser.add_argument("--stage", type=int, action="append", default=[],
                        help="a stage of 04 to turn into issues; repeat it: --stage 0 --stage 1")
    parser.add_argument("--refresh", action="store_true",
                        help="copy changed cards into their open issues, and add missing labels")
    parser.add_argument("--dry-run", action="store_true", help="read GitHub, change nothing, say what would change")
    parser.add_argument("--repo", help="OWNER/NAME (default: the GitHub repo of this folder)")
    args = parser.parse_args(argv)

    plan = Plan(PLAN_FILE.read_text(encoding="utf-8"))
    unknown = [stage for stage in args.stage if stage not in plan.stage_names]
    if unknown:
        parser.error(f"the plan has no stage {unknown[0]}; it has {sorted(plan.stage_names)}")
    if "plan" in args.commands:
        print_plan(plan, args.stage)
    steps = [name for name in STEPS if name in args.commands or "all" in args.commands]
    if not steps:
        return 0
    if "issues" in steps and not args.stage:
        parser.error("issues needs at least one --stage, for example: --stage 0 --stage 1")

    if subprocess.run(["gh", "auth", "status"], capture_output=True).returncode != 0:
        raise SystemExit("gh is not logged in. Run: gh auth login")
    info = json.loads(run_gh(["repo", "view", *([args.repo] if args.repo else []),
                              "--json", "nameWithOwner,visibility,owner"]))
    gh = GitHub(info["nameWithOwner"], args.dry_run)
    ctx = Context(gh, plan, info["owner"]["login"], info["visibility"] == "PUBLIC", args.stage, args.refresh)
    print(f"{'Dry run on' if gh.dry_run else 'Syncing'} {gh.repo} ({info['visibility'].lower()})")

    try:
        for name in steps:
            print(f"\n== {name}")
            STEPS[name](ctx)
    except GitHubError as error:
        print(f"\n✗ {error}\n\nThe steps before this one are done. Fix the cause and run the same "
              "command again — it skips what already exists.", file=sys.stderr)
        return 1

    if gh.dry_run:
        print(f"\nDry run: {gh.changes} change(s) would be made. Nothing was changed.")
        if "board" in steps:
            print("(A dry run can't show board cards for issues it would only create.)")
    else:
        print(f"\nDone: {gh.changes} change(s). Running it again changes nothing.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
