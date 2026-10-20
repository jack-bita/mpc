"""test_same_postgres.py — proves CI tests on the same PostgreSQL that every laptop runs.

The image tag is written twice: in compose.dev.yml (the laptop) and in .github/workflows/ci.yml
(the CI service container). Dependabot updates the first and never the second, so after its first
image PR the two would quietly differ, and CI would test a database nobody runs (REPO-5).
This test turns that PR red until ci.yml names the same tag, in the same PR.

It lives with the other tests in scripts/ because `make check`, and so CI, already runs them.
Run:  python3 -m unittest discover -s scripts
(Standard library only.)
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMPOSE_FILE = ROOT / "compose.dev.yml"
CI_FILE = ROOT / ".github" / "workflows" / "ci.yml"

# An `image: postgres:<tag>` line; comment lines don't count.
POSTGRES_IMAGE = re.compile(r"^\s*image:\s*(postgres:\S+)", re.MULTILINE)


def postgres_images(text: str) -> list[str]:
    return POSTGRES_IMAGE.findall(text)


class SamePostgresTest(unittest.TestCase):
    def test_the_finder_reads_an_image_line(self) -> None:
        # Without this, two files where the finder sees nothing would "agree" and pass.
        self.assertEqual(postgres_images("    image: postgres:18.6-alpine\n# image: postgres:9\n"),
                         ["postgres:18.6-alpine"])

    def test_ci_and_compose_name_the_same_postgres(self) -> None:
        compose = postgres_images(COMPOSE_FILE.read_text(encoding="utf-8"))
        ci = postgres_images(CI_FILE.read_text(encoding="utf-8"))
        self.assertEqual(len(compose), 1, f"expected one postgres image in {COMPOSE_FILE.name}, found {compose}")
        self.assertEqual(len(ci), 1, f"expected one postgres image in {CI_FILE.name}, found {ci}")
        self.assertEqual(ci, compose, "ci.yml must use the same postgres tag as compose.dev.yml: change both together")


if __name__ == "__main__":
    unittest.main()
