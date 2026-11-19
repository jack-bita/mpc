"""apps/people/tests/conftest.py — the `keyboard` fixture: the superuser's answers, typed in a test (PPL-13).

The superuser's commands (apps/people/management/commands/) ask at the keyboard with input(). A test can't type, so it
hands the answers in, in order, and the fixture puts itself in input()'s place for the test:

    keyboard.type("Duka la Mfano", "MFANO", "D", "Dawa", "", "", "n", "y")
    call_command("open_shop", stdout=out)

Each question takes the next answer, and the fixture keeps the questions asked (`asked`). A question with no answer
left fails the test at once, naming the question, so a command that asks one more than the test expects says which.
Answers left over fail the test when it ends, so a command that asks one fewer can't pass by luck.
"""

from collections.abc import Iterator

import pytest


class Keyboard:
    def __init__(self) -> None:
        self.answers: list[str] = []
        self.asked: list[str] = []

    def type(self, *answers: str) -> None:
        self.answers.extend(answers)

    def input(self, prompt: object = "") -> str:
        self.asked.append(str(prompt))
        if not self.answers:
            pytest.fail(f"No answer typed for: {prompt}")
        return self.answers.pop(0)


@pytest.fixture
def keyboard(monkeypatch: pytest.MonkeyPatch) -> Iterator[Keyboard]:
    keys = Keyboard()
    # builtins.input, the one every module calls by that name, and only for this test: monkeypatch puts it back.
    monkeypatch.setattr("builtins.input", keys.input)
    yield keys
    assert keys.answers == [], f"Typed but never asked: {keys.answers}"
