"""test_github_sync.py — proves github_sync.py reads the build plan correctly.

Two kinds of test:
- FormatTest reads a small sample plan holding every shape the script must
  understand: a full card, a card with no meta line, a one-line table row, a
  go-live row, and the §1, §4 and §15 tables. These don't change when the plan does.
- RealPlanTest reads docs/04-build-plan.md the same way. If a card heading or a
  table header is changed so the script can no longer read it, it fails here —
  not later, as a task that silently never became an issue.

Run:  python3 -m unittest discover -s scripts
(Standard library only, and no GitHub: nothing here talks to the network.)
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import github_sync as gs  # noqa: E402  (the import needs the path line above)

SAMPLE = """\
# 04 — Build Plan

## 1. The plan on one page

| Stage | Ends with | Milestone | Rough hours |
|---|---|---|---|
| 0 Groundwork | CI green, the demo deploys itself | Foundation | 30–45 |
| 3 Ready for real data | Production server, tested backups and alerts | Foundation | 25–35 |
| 4 Attendance live (R1b) | Every worker clocks in; the first month's pay is calculated | R1b · Attendance | 45–60 |

| Hours a week | Offline demo | Attendance ready | Drugs side ready |
|---|---|---|---|
| 30 | mid-December 2026 | end of December 2026 | mid-February 2027 |

## 3. How every task runs

```markdown
### CORE-2 · Tenancy guard that fails closed
`M` · Jack-led · after SHOP-1 · branch `feat/core-2-tenancy-guard`
```

## 4. GitHub setup

- **Milestones:** `Foundation` (stages 0–3) · `R1b · Attendance` · `R1 · Drugs`.

| Code | Epic | Code | Epic |
|---|---|---|---|
| `REPO` | Repository, tooling, CI | `ATT` | Attendance |
| `SPIKE` | Questions answered by a quick experiment | `OPS` | Images, servers, deploys, backups, monitoring |
| `LIVE` | Going live (mostly not code) | `FOLIO` | Portfolio |

## 5. Stage 0 — Groundwork

**Goal:** an empty but real repo.

### REPO-1 · Repository and GitHub setup
Done in **portion 6**, in chat — not with Claude Code.
**Done when:**
- [ ] A public GitHub repo.

### REPO-2 · Backend skeleton
`M` · Claude-led · after REPO-1 · branch `chore/repo-2-backend-skeleton`
**Learn:** a uv project.
**Tests:** `test_health_returns_ok`

### SPIKE-1 · Offline on the real shop devices
`M` · Jack-led · after OPS-2 · needs OWN-2 · branch `spike/spike-1-pwa-offline`
**Question:** does the static app install?

## 8. Stage 3 — Ready for real data

| ID | Task | Size | After | Done when |
|---|---|---|---|---|
| OPS-4 | Production server — Lineserve 2 GB, Dar es Salaam *(Jack-led)* | M | OPS-1 | SSH keys only, firewall (web and SSH) |

## 9. Stage 4 — Attendance live (R1b)

| ID | Task | Size | After | Done when |
|---|---|---|---|---|
| ATT-2 | Attendance rules and holidays | S | SHOP-3 | The answers from OWN-7 as dated settings |
| LIVE-1 | Attendance go-live | — | all of the above | §16 |

## 15. Shop and owner track

| ID | What | Who | Needed by |
|---|---|---|---|
| OWN-2 | Shop devices: which laptops and phones | Jack | SPIKE-1 |
| OWN-3 | Product name and web address | Jack + owner | OPS-4 |
| OWN-9 | The product sheet filled in — **start in stage 1** | Jack + siblings | ATT-2 |
| OWN-15 | BRELA papers — only if the address is a `.co.tz` | Owner | OWN-3 |
| OWN-16 | Baselines (spec §12) | Jack | before each go-live |

## 16. Going live
"""


class FormatTest(unittest.TestCase):
    """Every shape of the plan the script reads, on a small sample."""

    def setUp(self) -> None:
        self.plan = gs.Plan(SAMPLE)

    def test_reads_the_stage_table_and_ignores_the_others(self) -> None:
        self.assertEqual(self.plan.stage_names, {0: "0 Groundwork", 3: "3 Ready for real data",
                                                 4: "4 Attendance live (R1b)"})
        self.assertEqual(self.plan.milestone_of(4), "R1b · Attendance")

    def test_example_card_in_a_code_block_is_ignored(self) -> None:
        self.assertNotIn("CORE-2", self.plan.tasks)

    def test_reads_epics_and_milestones(self) -> None:
        self.assertEqual(self.plan.epics["REPO"], "Repository, tooling, CI")
        self.assertEqual(list(self.plan.epics), ["REPO", "ATT", "SPIKE", "OPS", "LIVE", "FOLIO"])
        self.assertEqual(self.plan.milestones, ["Foundation", "R1b · Attendance", "R1 · Drugs"])

    def test_reads_a_full_card(self) -> None:
        task = self.plan.tasks["REPO-2"]
        self.assertEqual((task.stage, task.size, task.mode, task.branch, task.is_card),
                         (0, "M", "Claude-led", "chore/repo-2-backend-skeleton", True))
        self.assertTrue(task.body.startswith("`M` · Claude-led"))
        self.assertTrue(task.body.endswith("`test_health_returns_ok`"))
        self.assertEqual(task.labels, ["type:chore", "size:M", "mode:claude-led"])

    def test_card_without_a_meta_line(self) -> None:
        task = self.plan.tasks["REPO-1"]
        self.assertEqual((task.size, task.mode, task.branch), (None, None, None))
        self.assertEqual(task.labels, ["type:chore"])
        self.assertIn("Done in **portion 6**", task.body)

    def test_needs_adds_the_needs_owner_label(self) -> None:
        task = self.plan.tasks["SPIKE-1"]
        self.assertEqual(task.needs, ["OWN-2"])
        self.assertEqual(task.labels, ["type:spike", "size:M", "mode:jack-led", "needs-owner"])

    def test_reads_a_one_line_row(self) -> None:
        task = self.plan.tasks["OPS-4"]
        self.assertEqual(task.title, "Production server — Lineserve 2 GB, Dar es Salaam")
        self.assertEqual((task.stage, task.size, task.mode, task.is_card), (3, "M", "Jack-led", False))
        self.assertEqual(task.labels, ["type:ops", "size:M", "mode:jack-led"])
        self.assertIn("**Done when:** SSH keys only", task.body)

    def test_a_row_without_a_marker_is_claude_led(self) -> None:
        self.assertEqual(self.plan.tasks["ATT-2"].labels, ["type:feat", "size:S", "mode:claude-led"])

    def test_go_live_row_has_no_size_or_mode(self) -> None:
        task = self.plan.tasks["LIVE-1"]
        self.assertEqual((task.size, task.mode), (None, None))
        self.assertEqual(task.labels, ["type:ops"])

    def test_owner_items_and_their_stage(self) -> None:
        self.assertEqual(self.plan.owner_items["OWN-9"].what, "The product sheet filled in — start in stage 1")
        self.assertEqual(self.plan.stage_of(self.plan.owner_items["OWN-2"]), 0)   # SPIKE-1
        self.assertEqual(self.plan.stage_of(self.plan.owner_items["OWN-15"]), 3)  # → OWN-3 → OPS-4
        self.assertEqual(self.plan.stage_of(self.plan.owner_items["OWN-16"]), 0)  # no task: now

    def test_issue_bodies_say_where_the_card_lives(self) -> None:
        self.assertIn("issues --stage 0 --refresh", gs.task_body(self.plan.tasks["REPO-2"]))
        self.assertIn("(04 BP2)", gs.task_body(self.plan.tasks["OPS-4"]))
        self.assertIn("never here", gs.owner_body(self.plan.owner_items["OWN-3"]))

    def test_an_id_used_twice_is_reported(self) -> None:
        plan = gs.Plan(SAMPLE + "\n## 20. Stage 0 — again\n\n### REPO-2 · Backend skeleton again\n")
        self.assertEqual(plan.duplicates, ["REPO-2"])
        self.assertEqual(plan.tasks["REPO-2"].title, "Backend skeleton")

    def test_ruleset_comparison_ignores_defaults_github_adds(self) -> None:
        import copy
        import json
        wanted = json.loads(gs.RULESET_FILE.read_text(encoding="utf-8"))
        stored = copy.deepcopy(wanted)
        for rule in stored["rules"]:
            if rule["type"] == "pull_request":
                rule["parameters"]["required_reviewers"] = []  # a default GitHub fills in
        self.assertTrue(gs.ruleset_matches(stored, wanted))
        rule = next(r for r in stored["rules"] if r["type"] == "pull_request")
        rule["parameters"]["allowed_merge_methods"] = ["merge", "squash"]
        self.assertFalse(gs.ruleset_matches(stored, wanted))


@unittest.skipUnless(gs.PLAN_FILE.exists(), "docs/04-build-plan.md is not in this checkout")
class RealPlanTest(unittest.TestCase):
    """The real plan reads the way the script expects."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.plan = gs.Plan(gs.PLAN_FILE.read_text(encoding="utf-8"))

    def test_every_stage_has_tasks_and_a_known_milestone(self) -> None:
        self.assertEqual(sorted(self.plan.stage_names), list(range(8)))
        for stage in self.plan.stage_names:
            with self.subTest(stage=stage):
                self.assertTrue(self.plan.tasks_in([stage]))
                self.assertIn(self.plan.milestone_of(stage), self.plan.milestones)

    def test_no_id_is_used_twice(self) -> None:
        self.assertEqual(self.plan.duplicates, [])

    def test_every_task_belongs_to_a_known_epic(self) -> None:
        unknown = sorted({task.epic for task in self.plan.tasks.values()} - set(self.plan.epics))
        self.assertEqual(unknown, [])

    def test_near_cards_name_size_mode_and_branch(self) -> None:
        # Stages 0–2 have full cards (04 BP2); REPO-1 alone is done in chat.
        for task in self.plan.tasks_in([0, 1, 2]):
            if task.id == "REPO-1":
                continue
            with self.subTest(task=task.id):
                self.assertTrue(task.is_card)
                self.assertIn(task.size, ("S", "M"))
                self.assertIn(task.mode, ("Jack-led", "Claude-led"))
                self.assertTrue(task.branch)

    def test_every_owner_item_lands_in_a_milestone(self) -> None:
        self.assertTrue(self.plan.owner_items)
        for item in self.plan.owner_items.values():
            with self.subTest(item=item.id):
                self.assertIn(self.plan.milestone_of(self.plan.stage_of(item)), self.plan.milestones)


if __name__ == "__main__":
    unittest.main()
