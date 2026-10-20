#!/usr/bin/env python3
"""check_commit_message.py — the commit-msg hook: refuses a commit whose message breaks 04 §3.5.

What it is for
--------------
Every commit says what it does and why it is needed (04 §3.5):

    type(scope): what it does, in the present tense

    Why: one or two sentences on why this change is needed now.

A habit can be forgotten; a hook can't. git runs this script after the message is written
and before the commit is made, passing the path of the file that holds the message. A
non-zero exit makes git refuse the commit, and git keeps the message in .git/COMMIT_EDITMSG
so nothing typed is lost.

pre-commit installs it (.pre-commit-config.yaml, `make hooks`). Only the squash commit of a
pull request reaches `main`, and REPO-7 checks those titles on GitHub; this hook covers the
commits on the laptop. Tests: scripts/test_check_commit_message.py.
Standard library only, and Python 3.10+, like the other scripts here.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# The types of 04 §3.5. A new type is a docs change first, then this line.
TYPES = ("feat", "fix", "test", "refactor", "docs", "chore", "ci", "build", "perf")

# `type: subject` or `type(scope): subject`. The scope is the app or area, in lower case
# (`core`, `sales`, `deps`); the subject must hold some text after one space.
SUBJECT = re.compile(rf"^(?:{'|'.join(TYPES)})(?:\([a-z0-9][a-z0-9-]*\))?: \S")

# The subjects git writes for a merge (`git merge origin/main`, 04 §3.4). They pass as they are:
# a merge brings in commits that were each checked already. Two conditions, so neither is a way
# around the rule: git's own wording, and git really merging (see `merging` in main()).
GIT_MERGE = re.compile(r"^Merge (?:remote-tracking )?(?:branch|branches|tag|tags|commit|commits) '")

# A `Why:` line with some text after it.
WHY = re.compile(r"^Why:\s*\S")

# `git commit -v` shows the diff below this line, and git cuts everything from it off.
SCISSORS = "# ------------------------ >8 ------------------------"

SHAPE = """\
The shape (04 §3.5):

    type(scope): what it does, in the present tense

    Why: one or two sentences on why this change is needed now.

Types: {types}. The scope is optional.
Your message is kept in .git/COMMIT_EDITMSG; commit again with the fix.
Never skip this check with --no-verify.""".format(types=", ".join(TYPES))


def message_lines(text: str) -> list[str]:
    """The lines git will keep: without its comment lines, the scissors part, and blank edges.

    The hook sees the message before git cleans it up, so it does that cleanup itself first.
    git drops `#` lines from an editor message by default, but keeps them in a `git commit -m` one;
    `make hooks` sets commit.cleanup=strip, so git drops them every time and agrees with this.
    git's comment character is `#` unless core.commentChar changes it; this repo leaves the default.
    """
    lines: list[str] = []
    for line in text.splitlines():  # splitlines also takes Windows line endings (\r\n)
        if line == SCISSORS:
            break
        if line.startswith("#"):
            continue
        lines.append(line.rstrip())
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    return lines


def problems(text: str, merging: bool = False) -> list[str]:
    """Everything wrong with one commit message, in plain words. An empty list means it passes.

    `merging` is True only while git is making a merge commit; then git's own merge subject passes.
    """
    lines = message_lines(text)
    if not lines:
        return ["The message is empty."]
    subject = lines[0]
    if merging and GIT_MERGE.match(subject):
        return []

    found: list[str] = []
    if not SUBJECT.match(subject):
        found.append(f"The first line must start with a type from the list, then `: ` and the subject. Got: {subject!r}")
    if len(lines) > 1 and lines[1]:
        found.append("The second line must be a blank line: it separates the subject from the reason.")
    if not any(WHY.match(line) for line in lines[1:]):
        found.append("A `Why:` line with the reason is missing. Every commit needs a strong reason.")
    return found


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: check_commit_message.py <file holding the commit message>", file=sys.stderr)
        return 2
    message_file = Path(argv[0])
    text = message_file.read_text(encoding="utf-8")
    # While git makes a merge commit, it keeps MERGE_HEAD in its own folder, the one that also holds
    # the message file (.git/COMMIT_EDITMSG or .git/MERGE_MSG; in a worktree, that worktree's folder).
    merging = (message_file.parent / "MERGE_HEAD").exists()
    found = problems(text, merging)
    if not found:
        return 0
    print("Commit refused: the message doesn't follow 04 §3.5.", file=sys.stderr)
    for problem in found:
        print(f"  - {problem}", file=sys.stderr)
    print(f"\n{SHAPE}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
