"""test_check_pr_title.py — proves check_pr_title.py lets through exactly the pull request
titles 04 §3.5 allows, under the commit hook's own subject rule.

Three groups:
- TitleTest: titles that must pass (ours, release-please's, Dependabot's) and titles that
  must be refused, starting with the card's own example, "update stuff" (REPO-7).
- SameRuleTest: the title check and the commit hook share one rule, so they can't drift apart.
- MainTest: the workflow's side: the exit code GitHub reads, and the explanation printed.

Run:  python3 -m unittest discover -s scripts
(Standard library only, like the script: the workflow runs it with the runner's own python3.)
"""

from __future__ import annotations

import io
import sys
import unittest
from contextlib import redirect_stderr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_commit_message as ccm  # noqa: E402  (the imports need the path line above)
import check_pr_title as cpt  # noqa: E402


class TitleTest(unittest.TestCase):
    def assert_passes(self, title: str) -> None:
        self.assertEqual(cpt.problems(title), [], title)

    def assert_refused(self, title: str) -> None:
        self.assertTrue(cpt.problems(title), f"should be refused: {title!r}")

    def test_update_stuff_is_refused(self) -> None:
        # REPO-7's Done when: this title must fail, because it would become a commit on main
        # that says nothing about what changed, and a changelog that can't sort it.
        self.assert_refused("update stuff")

    def test_a_conventional_title_passes(self) -> None:
        # A title is a subject only: no `Why:` line. The reason goes in the PR body, which
        # becomes the squash commit's body (the merge settings in scripts/github_sync.py).
        self.assert_passes("ci: check pull request titles")
        self.assert_passes("feat(core): tenancy guard raises without a shop")

    def test_release_please_titles_pass(self) -> None:
        # release-please opens its release PR with titles like these, and the ruleset requires
        # this check on that PR too. A refused title there would block every release.
        self.assert_passes("chore(main): release 0.1.0")
        self.assert_passes("chore(main): release mpc 1.0.0")  # the shape with a component name

    def test_dependabot_titles_pass(self) -> None:
        # .github/dependabot.yml gives its PRs these titles, and each becomes a squash commit.
        self.assert_passes("build(deps): bump django from 6.1.2 to 6.1.3")
        self.assert_passes("ci(deps): bump actions/checkout from 7.0.1 to 7.0.2")

    def test_githubs_default_title_is_refused(self) -> None:
        # For a PR with several commits, GitHub suggests a title made from the branch name.
        # Merged as it is, it would land on main with no type.
        self.assert_refused("Ci/repo 7 release please")

    def test_titles_that_break_the_shape_are_refused(self) -> None:
        for title in (
            "feature: add login",  # not a type of 04 §3.5
            "Feat: add login",  # types are lower case
            "ci:check titles",  # no space after the colon
            "feat(Core): tenancy guard",  # scopes are lower case
            "ci: ",  # no subject
            "",
        ):
            self.assert_refused(title)


class SameRuleTest(unittest.TestCase):
    def test_the_rule_is_the_commit_hooks_rule(self) -> None:
        # The very same object, not a copy: a change to the hook's rule changes this check too,
        # so a subject never passes on the laptop and fails on GitHub, or the other way round.
        self.assertIs(cpt.SUBJECT, ccm.SUBJECT)
        self.assertIs(cpt.TYPES, ccm.TYPES)


class MainTest(unittest.TestCase):
    def run_main(self, argv: list[str]) -> tuple[int, str]:
        err = io.StringIO()
        with redirect_stderr(err):
            code = cpt.main(argv)
        return code, err.getvalue()

    def test_a_good_title_exits_0_quietly(self) -> None:
        self.assertEqual(self.run_main(["ci: check pull request titles"]), (0, ""))

    def test_a_bad_title_exits_1_and_shows_the_rule(self) -> None:
        # A non-zero exit is what turns the `pr-title` check red on the pull request.
        code, printed = self.run_main(["update stuff"])
        self.assertEqual(code, 1)
        self.assertIn("update stuff", printed)  # the title it judged, so the log is clear
        self.assertIn("04 §3.5", printed)
        self.assertIn("type(scope)", printed)

    def test_wrong_usage_exits_2_and_says_how(self) -> None:
        # Exit 2, not 1: a broken workflow step, not a bad title.
        code, printed = self.run_main([])
        self.assertEqual(code, 2)
        self.assertIn("usage", printed)


if __name__ == "__main__":
    unittest.main()
