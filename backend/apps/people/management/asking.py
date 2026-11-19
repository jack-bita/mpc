"""apps/people/management/asking.py — how the superuser's commands ask at the keyboard, and how they refuse (PPL-13).

The superuser types these commands on the server: he is nobody's worker, so no office page can serve him, and the admin
opens no shop's rows (PPL-13, parking lot item 15). Each command asks its questions one at a time, and refuses the same
way. This module owns that shared part:

- Asker: one question at a time: a line of text, one word from a short list, yes or no, and a PIN typed twice, unseen.
- refuse_on_demo: the commands are refused where the demo seed runs.
- find_shop: the shop a command acts on, by its code.
- refused: a service's refusal, as the command's error, with its code and English words.

Only the shape of an answer is checked here, never a rule. A blank answer, or a word not on the list, is asked again,
as nothing was typed that a service could judge. Every rule (a taken code, a taken phone) is the services' own, reused
and never copied (the card's Watch out): asked here too, it could drift from theirs. One rule is asked early: the PIN's
strength, by calling check_pin_strength, the rule's own function, so a PIN refused at the very end doesn't throw away
every answer typed before it (Jack, PPL-13: 2A). set_pin asks it again anyway.
"""

import getpass
from collections.abc import Mapping

from django.conf import settings
from django.core.exceptions import NON_FIELD_ERRORS, ValidationError
from django.core.management.base import CommandError, OutputWrapper

from apps.people.pins import check_pin_strength
from apps.shops.models import Shop


class Asker:
    """Asks the superuser, one question at a time, and says why an answer is asked again. Writes through the command's
    own output (`out`), so a test reads what the command said."""

    def __init__(self, out: OutputWrapper) -> None:
        self._out = out

    def say(self, line: str) -> None:
        self._out.write(line)

    def text(self, question: str, *, default: str = "", optional: bool = False) -> str:
        """A line of text, trimmed. Blank takes the `default`, or "" if the answer is `optional`; otherwise it is asked
        again."""
        shown = f"{question} [{default}]: " if default else f"{question}: "
        while True:
            # input() shows the question and waits for Enter. Spaces around an answer are never meant: a code typed
            # " MPC" is MPC.
            answer = input(shown).strip()
            if answer or optional:
                return answer
            if default:
                return default
            self.say("An answer is needed.")

    def choice[T](self, question: str, words: Mapping[str, T], *, default: str) -> T:
        """One of a few `words`, in small or capital letters; blank takes the `default`. Anything else is asked again,
        with the words listed, so a typo never becomes a value nobody chose."""
        listed = "/".join(words)
        while True:
            answer = self.text(f"{question} ({listed})", default=default).lower()
            if answer in words:
                return words[answer]
            self.say(f"Type one of: {', '.join(words)}.")

    def yes(self, question: str) -> bool:
        """Yes only for y or yes. Blank, or anything else, is no: each yes here writes to a real shop, so it must be
        typed, never taken from a slip of the Enter key."""
        return input(f"{question} [y/N]: ").strip().lower() in {"y", "yes"}

    def pin(self) -> str:
        """A new PIN, typed twice and never shown (the card's default). getpass reads from the keyboard with the
        screen's echo off, so the PIN never shows on the screen, in the terminal's scrollback, or in the shell's
        history, and never appears in the server's list of running programs, where an argument would (`ps`). Two that
        differ, or a PIN its rule refuses, are asked again at once."""
        while True:
            first = getpass.getpass("New PIN, 4 digits (not shown): ")
            if getpass.getpass("The same PIN again: ") != first:
                self.say("The two PINs differ. Type them again.")
                continue
            try:
                # The rule's own function, called, never copied (Jack, PPL-13: 2A): too short, or one a coworker would
                # guess first.
                check_pin_strength(first)
            except ValidationError as error:
                # The PIN itself is never in the words: only the code and why.
                self.say(f"{error.code}: {' '.join(error.messages)} Type another.")
                continue
            return first


def refuse_on_demo() -> None:
    """Refuse where the demo seed runs (settings.DEMO_SEED): its seed makes its own shop and people, and keeps them as
    made each day (DATA-1). Asked before anything else, so nothing is even asked there (the card's default)."""
    if settings.DEMO_SEED:
        raise CommandError("Refused on the demo: its seed makes its own shop and people, and keeps them as made.")


def find_shop(code: str) -> Shop:
    """The shop with this code, typed as people write it: " mpc " is MPC, as Shop.clean stores it. The shop's own row is
    no shop's row (it has no `shop`), so it is read with no shop open; the command then opens it (shop_context)."""
    shop = Shop.objects.filter(code=code.strip().upper()).first()
    if shop is None:
        raise CommandError(f"No shop has the code {code.strip().upper()}. Its code is the one open_shop printed.")
    return shop


def refused(error: ValidationError) -> CommandError:
    """A service's refusal as the command's error: each code with its English words, and the field it is about, one per
    line. CommandError, so Django prints it with no traceback, and the command exits with 1 (as seed_demo does). Every
    service called here keeps all or nothing, so nothing was written."""
    lines = ["Refused, nothing written:"]
    for field, errors in _by_field(error):
        where = "" if field == NON_FIELD_ERRORS else f" ({field})"
        for one in errors:
            # Iterating one error gives its words with their values filled in, as the API's answer does.
            for words in one:
                lines.append(f"  {one.code or 'invalid'}{where}: {words}")
    return CommandError("\n".join(lines))


def _by_field(error: ValidationError) -> list[tuple[str, list[ValidationError]]]:
    # A ValidationError holds either errors by field (`error_dict`, as full_clean raises them) or a plain list
    # (`error_list`, as a service's own check raises one). Both read the same way here: a plain list is about no field.
    if hasattr(error, "error_dict"):
        return list(error.error_dict.items())
    return [(NON_FIELD_ERRORS, error.error_list)]
