"""apps/people/tests/conftest.py — the `keyboard` fixture: the superuser's answers, typed in a test (PPL-13).

The Keyboard itself, and how a test types with it, is in backend/tests/keyboard.py. This fixture puts one in place of
input() and getpass for one test, and fails the test when answers are left over, so a command that asks one question
fewer than the test expects can't pass by luck.
"""

from collections.abc import Iterator

import pytest

from tests.keyboard import Keyboard


@pytest.fixture
def keyboard(monkeypatch: pytest.MonkeyPatch) -> Iterator[Keyboard]:
    keys = Keyboard()
    # builtins.input, the one every module calls by that name, and getpass.getpass, the one asking.py calls through
    # its module, only for this test: monkeypatch puts both back.
    monkeypatch.setattr("builtins.input", keys.input)
    monkeypatch.setattr("getpass.getpass", keys.getpass)
    yield keys
    assert (keys.answers, keys.pins) == ([], []), f"Typed but never asked: {keys.answers}, {len(keys.pins)} PINs"
