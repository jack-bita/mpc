#!/usr/bin/env python3
"""check_pr_title.py — the pull request title check: refuses a title that breaks 04 §3.5.

What it is for
--------------
Every pull request is squash-merged, and its title becomes the one commit on `main`
(04 BP11). release-please then reads that commit to write the changelog and pick the next
version. So a title like "update stuff" must fail before the merge, while it can still be
edited, not after, when `main` is never rewritten.

A title is a subject only:

    type(scope): what it does, in the present tense

Its reason is the PR body's *What and why*, which becomes the squash commit's body.

The rule is not written twice: SUBJECT and TYPES come from check_commit_message.py, the
commit hook. A subject that passes on the laptop passes here, and the other way round.

.github/workflows/pr-title.yml runs it on GitHub, with the title as its one argument.
Tests: scripts/test_check_pr_title.py. Standard library only, and Python 3.10+, like the
other scripts here, so the workflow needs no setup step.
"""

from __future__ import annotations

import sys

from check_commit_message import SUBJECT, TYPES

SHAPE = """\
The title becomes the one commit on main (04 BP11), so it takes a commit subject's shape (04 §3.5):

    type(scope): what it does, in the present tense

Types: {types}. The scope is optional.
Edit the title on GitHub: this check runs again by itself.""".format(types=", ".join(TYPES))


def problems(title: str) -> list[str]:
    """Everything wrong with one pull request title, in plain words. An empty list means it passes."""
    if SUBJECT.match(title):
        return []
    return [f"The title must start with a type from the list, then `: ` and the subject. Got: {title!r}"]


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: check_pr_title.py <pull request title>", file=sys.stderr)
        return 2
    found = problems(argv[0])
    if not found:
        return 0
    print("Title refused: it doesn't follow 04 §3.5.", file=sys.stderr)
    for problem in found:
        print(f"  - {problem}", file=sys.stderr)
    print(f"\n{SHAPE}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
