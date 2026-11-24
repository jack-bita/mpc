"""backend/tests/test_flag_kinds.py — every kind of flag the server raises has its words on the flags' page, and so has
every note the server writes as a code (CTRL-4).

The server names 18 kinds (02 §13), and raises five today; each later card raises its own. The app shows a kind by its
words in both word books, and one it has no words for as "Tofauti nyingine", which tells a manager nothing. So this test
reads the kinds our code names anywhere, the books, and the app's own list, and holds the three together: a card that
raises a new kind fails here until its words are written; its sentence, the app's own type checker asks for
(flag-words.ts). It reads the app's files, as test_app_number.py does.

A note can be a code too, which the page says in words: the system's own (SYSTEM_NOTES), and on the demo a ready one
(DEMO_NOTES). One the app doesn't know would show as the bare code, so their lists are held together the same way.
"""

import ast
import json
import re
from pathlib import Path

from django.conf import settings

from apps.control.models import DEMO_NOTES, FlagKind
from apps.control.services import SYSTEM_NOTES

BACKEND = Path(settings.BASE_DIR)
FRONTEND = BACKEND.parent / "frontend"
WORDS_FILE = FRONTEND / "src" / "features" / "flags" / "flag-words.ts"


def kinds_named_in(folder: Path) -> set[str]:
    # Every `FlagKind.SOMETHING` in our code, but the migrations' and the tests', which raise nothing in a shop.
    kinds = set()
    for file in folder.rglob("*.py"):
        if {"migrations", "tests"} & set(file.parts):
            continue
        for node in ast.walk(ast.parse(file.read_text())):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "FlagKind":
                member = getattr(FlagKind, node.attr, None)
                if isinstance(member, FlagKind):
                    kinds.add(member.value)
    return kinds


def test_every_kind_raised_has_its_words() -> None:
    raised = kinds_named_in(BACKEND / "apps")
    # Not passed by looking at nothing: the push's own kinds are there.
    assert {"device_gap", "invalid_document"} <= raised

    for book in ("sw", "en"):
        words = json.loads((FRONTEND / "messages" / f"{book}.json").read_text())["flags"]["kind"]
        assert set(words) - {"another"} == raised, book

    listed = re.search(
        r"RAISED_KINDS = \[(.*?)\] as const", (FRONTEND / "src/features/flags/flags.ts").read_text(), flags=re.S
    )
    assert listed is not None
    assert set(re.findall(r'"(\w+)"', listed[1])) == raised


def codes_listed(name: str) -> set[str]:
    # The codes of one list of the app's, `const NAME = { code: "words", "a.code": "words" } as const`.
    listed = re.search(rf"const {name} = \{{(.*?)\}} as const", WORDS_FILE.read_text(), flags=re.S)
    assert listed is not None, name
    return {quoted or bare for quoted, bare in re.findall(r'(?:"([\w.]+)"|(\w+)): "\w+"', listed[1])}


def test_every_note_written_as_a_code_has_its_words() -> None:
    assert codes_listed("SYSTEM_NOTES") == set(SYSTEM_NOTES.values())
    assert codes_listed("READY_NOTES") == set(DEMO_NOTES)
