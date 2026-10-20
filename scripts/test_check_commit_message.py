"""test_check_commit_message.py — proves check_commit_message.py lets through exactly the
commit messages 04 §3.5 allows: `type(scope): subject`, a blank line, and a `Why:` line.

Three groups:
- GoodMessageTest: messages that must pass, including the shapes git itself writes
  (comment lines, the `git commit -v` diff, and, only during a real merge, the `Merge …`
  subjects of `git merge origin/main`).
- RefusedMessageTest: one test per way a message can break the rule.
- MainTest: the hook's side: the exit code git reads, and the explanation printed.

Run:  python3 -m unittest discover -s scripts
(Standard library only: git calls the hook before any project tooling is needed.)
"""

from __future__ import annotations

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_commit_message as ccm  # noqa: E402  (the import needs the path line above)

GOOD = "ci: backend checks\n\nWhy: every pull request is tested on a clean machine.\n"


class GoodMessageTest(unittest.TestCase):
    def assert_passes(self, message: str) -> None:
        self.assertEqual(ccm.problems(message), [], message)

    def test_subject_blank_line_and_why_pass(self) -> None:
        self.assert_passes(GOOD)

    def test_a_scope_in_brackets_is_allowed(self) -> None:
        self.assert_passes("feat(core): tenancy guard raises without a shop\n\nWhy: a query must fail loudly.\n")

    def test_every_type_of_section_3_5_passes(self) -> None:
        for type_ in ("feat", "fix", "test", "refactor", "docs", "chore", "ci", "build", "perf"):
            self.assert_passes(f"{type_}: do one thing\n\nWhy: it is needed now.\n")

    def test_why_may_come_after_other_body_lines(self) -> None:
        self.assert_passes("fix(money): expected cash counts cash change\n\nThe sum missed it.\n\nWhy: B3.\n")

    def test_gits_comment_lines_are_ignored(self) -> None:
        # What the editor shows for a plain `git commit`: git removes these lines itself later.
        self.assert_passes(GOOD + "# Please enter the commit message for your changes.\n#\n# On branch x\n")

    def test_the_diff_below_the_scissors_line_is_ignored(self) -> None:
        # `git commit -v` adds the diff below this line; git cuts it off before saving the commit.
        self.assert_passes(GOOD + "# ------------------------ >8 ------------------------\n+not: a subject\n")

    def test_a_message_with_windows_line_endings_passes(self) -> None:
        self.assert_passes(GOOD.replace("\n", "\r\n"))

    def test_gits_own_merge_messages_pass_during_a_merge(self) -> None:
        # `git merge origin/main` (04 §3.4) writes these itself, with no type and no Why.
        for message in (
            "Merge remote-tracking branch 'origin/main' into ci/repo-5-ci\n",
            "Merge branch 'main' into feat/core-2-tenancy-guard\n",
            "Merge branch 'main' of github.com:jack-bita/mpc into ci/repo-5-ci\n",  # the `git pull` shape
            "Merge branches 'a' and 'b'\n",
            "Merge tag 'v0.1.0'\n",
            "Merge commit '5457c92'\n",
        ):
            self.assertEqual(ccm.problems(message, merging=True), [], message)


class RefusedMessageTest(unittest.TestCase):
    def assert_refused(self, message: str, expected_words: str) -> None:
        found = ccm.problems(message)
        self.assertTrue(found, f"should be refused: {message!r}")
        self.assertIn(expected_words, " ".join(found))

    def test_a_message_with_no_why_line_is_refused(self) -> None:
        self.assert_refused("chore: try\n", "Why:")

    def test_an_empty_why_is_refused(self) -> None:
        self.assert_refused("chore: try\n\nWhy:\n", "Why:")
        self.assert_refused("chore: try\n\nWhy:   \n", "Why:")

    def test_a_why_below_the_scissors_line_does_not_count(self) -> None:
        self.assert_refused("chore: try\n\n# ------------------------ >8 ------------------------\nWhy: x\n", "Why:")

    def test_a_subject_without_a_type_is_refused(self) -> None:
        self.assert_refused("update stuff\n\nWhy: it changed.\n", "type")

    def test_a_type_not_in_section_3_5_is_refused(self) -> None:
        self.assert_refused("feature: add login\n\nWhy: staff sign in.\n", "type")

    def test_a_missing_space_after_the_colon_is_refused(self) -> None:
        self.assert_refused("ci:backend checks\n\nWhy: tested.\n", "type")

    def test_an_empty_subject_after_the_type_is_refused(self) -> None:
        self.assert_refused("ci: \n\nWhy: tested.\n", "type")

    def test_a_why_with_no_blank_line_before_it_is_refused(self) -> None:
        self.assert_refused("ci: backend checks\nWhy: tested.\n", "blank line")

    def test_a_merge_subject_git_did_not_write_is_refused(self) -> None:
        # Only git's own merge shapes skip the rule, so "Merge" can't be a way around it.
        found = ccm.problems("Merge the new screens\n", merging=True)
        self.assertIn("type", " ".join(found))

    def test_a_typed_merge_subject_is_refused_when_git_is_not_merging(self) -> None:
        # Typing git's wording by hand is no way around the rule either: no merge, no exception.
        self.assert_refused("Merge branch 'x' and skip the reason\n", "type")

    def test_an_empty_message_is_refused(self) -> None:
        self.assert_refused("# only a comment\n\n", "empty")


class MainTest(unittest.TestCase):
    def run_main(self, message: str, merging: bool = False) -> tuple[int, str]:
        # git hands the hook the path of a file holding the message (.git/COMMIT_EDITMSG). The
        # temporary folder plays the .git folder; during a merge, git keeps MERGE_HEAD there.
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "COMMIT_EDITMSG"
            path.write_text(message, encoding="utf-8")
            if merging:
                (Path(folder) / "MERGE_HEAD").write_text("5457c92\n", encoding="utf-8")
            err = io.StringIO()
            with redirect_stderr(err):
                code = ccm.main([str(path)])
        return code, err.getvalue()

    def test_a_good_message_exits_0_quietly(self) -> None:
        self.assertEqual(self.run_main(GOOD), (0, ""))

    def test_a_bad_message_exits_1_and_shows_the_rule(self) -> None:
        # A non-zero exit is what makes git refuse the commit.
        code, printed = self.run_main("chore: try\n")
        self.assertEqual(code, 1)
        self.assertIn("04 §3.5", printed)
        self.assertIn("Why:", printed)

    def test_a_merge_message_passes_only_while_git_is_merging(self) -> None:
        merge = "Merge remote-tracking branch 'origin/main' into ci/repo-5-ci\n"
        self.assertEqual(self.run_main(merge, merging=True), (0, ""))
        self.assertEqual(self.run_main(merge, merging=False)[0], 1)


if __name__ == "__main__":
    unittest.main()
