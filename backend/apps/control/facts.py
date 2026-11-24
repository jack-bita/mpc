"""apps/control/facts.py — what a flag's page says about the record the flag is about (CTRL-4).

A flag's subject is a row of one of several tables: a tap of Ingia, a pushed record's line, later a drawer's day. Each
table knows its own facts, and `control` is layer 0, which may not import them (ADR-0043). So `control` says what an
answer looks like, and each such table's model answers with `flag_facts()`: it imports this file, never the other way
round. A table that answers none still shows, with the flag's own facts alone.
"""

import uuid
from dataclasses import dataclass
from datetime import date
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class FlaggedTap:
    # A tap of Ingia or Toka: whose (their job), which of the two, and its day on the shop's calendar, for the page to
    # open that day, where it is decided (ATT-6).
    staff: uuid.UUID
    kind: str
    day: date


@dataclass(frozen=True)
class FlagFacts:
    # The tap the record is, if it is one: shown only when the flag names its worker (flag_detail), as a flag can be
    # about something else of the same record, its laptop's missing numbers or the file that brought it.
    tap: FlaggedTap | None = None
    # Why the server refused the record: an error's code, which the page says in words. Empty when it kept it.
    refused_for: str = ""
    # For a record brought in a rescue file (SYNC-12): the laptop that made it, and who loaded the file, by name and by
    # their job's id; and who made the record, by theirs, so the page can tell a flag about the loading from one about
    # the record (flag_detail), as both are about the same line.
    brought_from: str | None = None
    loaded_by: str | None = None
    loader: uuid.UUID | None = None
    maker: uuid.UUID | None = None


@runtime_checkable
class SaysItsFacts(Protocol):
    # A row a flag's page can say more about. Asked of one row, for one page: the list reads its records one query per
    # table, and never asks this.
    def flag_facts(self) -> FlagFacts: ...
