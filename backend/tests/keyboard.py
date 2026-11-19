"""backend/tests/keyboard.py — the superuser's answers, typed in a test (PPL-13).

The superuser's commands (apps/people/management/commands/) ask at the keyboard: input() for a line, and getpass for a
PIN, which is never shown. A test can't type, so it hands the answers in, in order, and a Keyboard stands in for both:

    keyboard.type("Duka la Mfano", "MFANO", "D", "Dawa", "", "", "n", "y")
    keyboard.type_pins("4826", "4826")
    call_command("open_shop", stdout=out)

Each question takes the next answer of its kind, and every question asked is kept (`asked`), a PIN's too. A question
with no answer left fails the test at once, naming the question, so a command that asks one more than the test expects
says which. The `keyboard` fixture (apps/people/tests/conftest.py) puts one in place for a test, and fails it when
answers are left over. A helper module, as tests/change_log.py is, so tests import it from here, never from a conftest.
"""

import pytest


class Keyboard:
    def __init__(self) -> None:
        self.answers: list[str] = []
        self.pins: list[str] = []
        self.asked: list[str] = []

    def type(self, *answers: str) -> None:
        self.answers.extend(answers)

    def type_pins(self, *pins: str) -> None:
        self.pins.extend(pins)

    def input(self, prompt: object = "") -> str:
        return self._next(self.answers, str(prompt))

    def getpass(self, prompt: str = "Password: ", stream: object = None, **unused: object) -> str:
        # getpass's own arguments, so a call that names them still lands here.
        return self._next(self.pins, prompt)

    def _next(self, typed: list[str], prompt: str) -> str:
        self.asked.append(prompt)
        if not typed:
            pytest.fail(f"No answer typed for: {prompt}")
        return typed.pop(0)
