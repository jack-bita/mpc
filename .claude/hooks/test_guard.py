"""test_guard.py — proves .claude/hooks/guard.py refuses what it should, and only that.

Each test builds a throwaway git repo, sends the guard the same JSON Claude Code would,
and checks the exit code: 2 = refused, 0 = allowed.

Run:  python3 -m unittest discover -s .claude/hooks
(Standard library only, so it runs before the backend's tools are installed.)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

GUARD = Path(__file__).with_name("guard.py")
APPLIED = "backend/apps/sales/migrations/0001_initial.py"
FIRST_USER = "backend/apps/people/migrations/0001_initial.py"


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


class GuardTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name).resolve()
        git(self.repo, "init", "-q", "-b", "main")
        git(self.repo, "config", "user.email", "test@example.com")
        git(self.repo, "config", "user.name", "Test")
        self.write(APPLIED, "# a migration that is already on main\n")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-q", "-m", "chore: initial")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    # -- helpers
    def write(self, rel: str, text: str = "x\n") -> None:
        path = self.repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def run_guard(self, tool: str, **tool_input: str) -> int:
        event = {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input, "cwd": str(self.repo)}
        env = {**os.environ, "CLAUDE_PROJECT_DIR": str(self.repo)}
        result = subprocess.run([sys.executable, str(GUARD)], input=json.dumps(event),
                                capture_output=True, text=True, env=env)
        return result.returncode

    def edit(self, rel: str) -> int:
        return self.run_guard("Edit", file_path=str(self.repo / rel), old_string="a", new_string="b")

    def bash(self, command: str) -> int:
        return self.run_guard("Bash", command=command)

    def on_task_branch(self) -> None:
        git(self.repo, "switch", "-q", "-c", "feat/core-2-tenancy-guard")

    # -- 1. generated files
    def test_generated_api_types_refused(self) -> None:
        self.assertEqual(self.edit("frontend/src/api/schema.d.ts"), 2)

    def test_changelog_refused_for_write_too(self) -> None:
        self.assertEqual(self.run_guard("Write", file_path=str(self.repo / "CHANGELOG.md"), content="x"), 2)

    def test_lock_files_refused(self) -> None:
        self.assertEqual(self.edit("backend/uv.lock"), 2)
        self.assertEqual(self.edit("frontend/pnpm-lock.yaml"), 2)

    def test_ordinary_file_allowed(self) -> None:
        self.assertEqual(self.edit("backend/apps/sales/services.py"), 0)

    def test_file_outside_repo_allowed(self) -> None:
        self.assertEqual(self.run_guard("Edit", file_path="/etc/hosts"), 0)

    # -- 2. migrations
    def test_migration_on_main_refused(self) -> None:
        self.on_task_branch()
        self.assertEqual(self.edit(APPLIED), 2)

    def test_new_migration_on_branch_allowed(self) -> None:
        self.on_task_branch()
        self.write("backend/apps/sales/migrations/0002_sale_lines.py")
        self.assertEqual(self.edit("backend/apps/sales/migrations/0002_sale_lines.py"), 0)

    # -- 3. migrate before PPL-1
    def test_migrate_refused_before_custom_user(self) -> None:
        self.assertEqual(self.bash("make migrate"), 2)
        self.assertEqual(self.bash("cd backend && uv run python manage.py migrate"), 2)

    def test_migrate_allowed_once_custom_user_exists(self) -> None:
        self.write(FIRST_USER)
        self.assertEqual(self.bash("make migrate"), 0)

    def test_makemigrations_check_allowed(self) -> None:
        self.assertEqual(self.bash("cd backend && uv run python manage.py makemigrations --check"), 0)

    # -- 4. main, force-push
    def test_commit_on_main_refused(self) -> None:
        self.assertEqual(self.bash('git commit -m "feat(core): x"'), 2)

    def test_commit_on_task_branch_allowed(self) -> None:
        self.on_task_branch()
        self.assertEqual(self.bash('git add -p && git commit -m "test(core): a query without a shop raises"'), 0)

    def test_force_push_refused(self) -> None:
        self.on_task_branch()
        self.assertEqual(self.bash("git push --force origin feat/core-2-tenancy-guard"), 2)
        self.assertEqual(self.bash("git push -f"), 2)
        self.assertEqual(self.bash("git push origin +feat/core-2-tenancy-guard"), 2)

    def test_push_to_main_refused(self) -> None:
        self.on_task_branch()
        self.assertEqual(self.bash("git push origin main"), 2)
        self.assertEqual(self.bash("git push origin HEAD:main"), 2)

    def test_bare_push_from_main_refused(self) -> None:
        self.assertEqual(self.bash("git push"), 2)

    def test_push_task_branch_allowed(self) -> None:
        self.on_task_branch()
        self.assertEqual(self.bash("git push -u origin feat/core-2-tenancy-guard"), 0)

    def test_git_with_global_options_still_checked(self) -> None:
        self.assertEqual(self.bash('git -C backend commit -m "x"'), 2)

    # -- 5. skipping the git hooks
    def test_no_verify_refused(self) -> None:
        self.on_task_branch()
        self.assertEqual(self.bash('git commit --no-verify -m "feat(core): x" -m "Why: y"'), 2)
        self.assertEqual(self.bash('git commit -n -m "feat(core): x"'), 2)
        self.assertEqual(self.bash("git push --no-verify -u origin feat/core-2-tenancy-guard"), 2)

    def test_message_mentioning_no_verify_allowed(self) -> None:
        self.on_task_branch()
        self.assertEqual(self.bash('git commit -m "docs: explain why we never use -n" -m "Why: hooks check every commit."'), 0)

    # -- 6. force-adding ignored files
    def test_force_add_refused(self) -> None:
        self.on_task_branch()
        self.assertEqual(self.bash("git add -f private/products.xlsx"), 2)

    # -- the guard never blocks ordinary work
    def test_read_only_commands_allowed(self) -> None:
        self.assertEqual(self.bash("git log --oneline main..HEAD && git status --short"), 0)
        self.assertEqual(self.bash("make check"), 0)

    def test_other_tools_ignored(self) -> None:
        self.assertEqual(self.run_guard("Read", file_path=str(self.repo / "CHANGELOG.md")), 0)

    def test_broken_input_is_a_warning_not_a_block(self) -> None:
        env = {**os.environ, "CLAUDE_PROJECT_DIR": str(self.repo)}
        result = subprocess.run([sys.executable, str(GUARD)], input="not json", capture_output=True, text=True, env=env)
        self.assertEqual(result.returncode, 1)


if __name__ == "__main__":
    unittest.main()
