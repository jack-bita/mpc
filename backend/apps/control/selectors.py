"""apps/control/selectors.py — the reads of the control tables the services and the office routes share (ADR-0015).

flag_names says whether a flag names a person: the services ask it before a flag is closed (02 §13), and a flag's page
asks it for the person looking. One question in one place, so the page and the service can't answer it differently.

flags_asked and in_state keep a list of flags to what the page asks, and flag_lines says each in the words of a line:
who it names, and the laptop and time of the record it is about. flag_detail says one flag whole: those, what its record
says of itself (apps/control/facts.py), and every note (CTRL-4).

`control` is layer 0 and may not import `people`, nor the apps whose records a flag is about (ADR-0043), so it reaches
their tables by their type codes (apps/core/links.py), at run time, as a flag's subject is, and reads only what `core`
gives every one of them: a counter record's laptop and time (CounterRecord).
"""

import uuid
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.db import models

from apps.control.facts import FlagFacts, SaysItsFacts
from apps.control.models import CLOSED, DEMO_NOTES, Flag, FlagNote, FlagPerson
from apps.core.links import table_of
from apps.core.models import CounterRecord
from apps.core.tenancy import Actor


def flag_names(flag: Flag, person: Actor) -> bool:
    """Whether `flag` names `person`, under any of their jobs at the shop: someone who left and was hired again has two
    (PPL-11), and a flag that names the old one is still about them (02 §13)."""
    # By the person, not the job: whoever the acting job belongs to, as deciding one's own day is asked (ATT-6). One
    # query: the jobs the flag names, whose person is the acting job's person. Both tables read through the shop's
    # guard, so a job at another shop never counts.
    jobs: Any = table_of("staff")
    their_person = jobs._default_manager.filter(pk=person.staff_id).values("user")
    return FlagPerson.objects.filter(flag=flag, staff__user__in=their_person).exists()


class FlagState(models.TextChoices):
    # The list's two tabs (CTRL-4). An explained flag still waits: only a close ends one (02 §13).
    WAITING = "waiting", "Waiting"
    CLOSED = "closed", "Closed"


def in_state(flags: models.QuerySet[Flag], state: str) -> models.QuerySet[Flag]:
    """The flags of one tab: those that wait for a person, or the closed ones."""
    if state == FlagState.CLOSED:
        return flags.filter(status__in=CLOSED)
    return flags.exclude(status__in=CLOSED)


def flags_asked(
    flags: models.QuerySet[Flag], *, kind: str | None, side_id: uuid.UUID | None, whole_shop: bool
) -> models.QuerySet[Flag]:
    """The flags *Chuja* asks for: of one kind, of one side, or of the whole shop alone. Nothing asked: them all.
    `flags`: the route's own rows, kept already to what the person may see."""
    if kind is not None:
        flags = flags.filter(kind=kind)
    if side_id is not None:
        flags = flags.filter(side=side_id)
    if whole_shop:
        flags = flags.filter(side__isnull=True)
    return flags


@dataclass(frozen=True)
class FlagLine:
    # One line of the list, as the page shows it: a flag's own facts, and the laptop and time of the record it is about.
    id: uuid.UUID
    kind: str
    status: str
    side: str | None
    people: list[str]
    device: str | None
    made_at: datetime | None
    raised_at: datetime


def flag_lines(flags: Sequence[Flag]) -> list[FlagLine]:
    """Each of `flags`, loaded with its side, as a line of the list, in their order: one query for the people they name,
    and one per table for the records they are about, however many flags there are (CTRL-1's note)."""
    named = people_named(flags)
    records = _records(flags)
    return [_line(flag, named[flag.pk], records.get(flag.subject_id)) for flag in flags]


def _line(flag: Flag, people: dict[uuid.UUID, str], record: CounterRecord | None) -> FlagLine:
    return FlagLine(
        id=flag.pk,
        kind=flag.kind,
        status=flag.status,
        side=None if flag.side is None else flag.side.name,
        people=list(people.values()),
        # A tap entered in the office has no laptop and no laptop's time (ATT-13).
        device=None if record is None or record.device_id is None else record.device.name,
        made_at=None if record is None else record.client_time,
        raised_at=flag.created_at,
    )


@dataclass(frozen=True)
class NoteLine:
    # One note of a flag, as its page shows it: what it did, its words, who and when. `by` is none for the system's own,
    # whose words are a code (SYSTEM_NOTES, apps/control/services.py).
    id: uuid.UUID
    step: str
    text: str
    by: str | None
    at: datetime


@dataclass(frozen=True)
class FlagDetail(FlagLine):
    # One flag whole, as its page shows it: its line, its numbers if it has them, what its record says of itself, its
    # notes, and whether it names the one looking, who may then only explain it (02 §13).
    expected: Decimal | None
    actual: Decimal | None
    difference: Decimal | None
    facts: FlagFacts
    # Whether it is about loading a rescue file, not about the record in it (SYNC-12): it names whoever loaded it, and
    # not the record's maker. One who loaded a record of their own has both in one person, and it reads as the record's.
    about_loading: bool
    notes: list[NoteLine]
    names_you: bool
    # On the demo, the ready notes an action may take (DEMO_NOTES), as codes the page says in words; elsewhere none, and
    # a person types their own.
    ready_notes: list[str]


def flag_detail(flag: Flag, *, viewer: Actor) -> FlagDetail:
    """`flag`, loaded with its side, whole, for its page, as `viewer` sees it: the person looking."""
    record = _records([flag]).get(flag.subject_id)
    named = people_named([flag])[flag.pk]
    # A record of a table that says nothing of itself, or none at all: the flag's own facts alone.
    facts = record.flag_facts() if isinstance(record, SaysItsFacts) else FlagFacts()
    if facts.tap is not None and facts.tap.staff not in named:
        # The record is a tap of someone the flag doesn't name, so the flag is not about it: missing numbers, whose line
        # is whatever record came after them (SYNC-5), or a rescue file's loading, which names whoever loaded it
        # (SYNC-12). Its day would say nothing of the flag, and nothing of that worker is anyone's to open from here.
        facts = replace(facts, tap=None)
    # Oldest first, as they were written: an explanation before the close that followed it. Who wrote each is read in
    # the same query.
    notes = FlagNote.objects.filter(flag=flag).select_related("created_by").order_by("created_at", "id")
    return FlagDetail(
        # Its line's own fields, so the page and the list can't say them differently.
        **vars(_line(flag, named, record)),
        expected=flag.expected,
        actual=flag.actual,
        difference=flag.difference,
        facts=facts,
        # By the people, never by their nicknames, which are unique among current workers alone.
        about_loading=facts.loader in named and facts.maker not in named,
        notes=[
            NoteLine(
                id=note.pk,
                step=note.step,
                text=note.text,
                by=None if note.created_by is None else note.created_by.display_name,
                at=note.created_at,
            )
            for note in notes
        ],
        names_you=flag_names(flag, viewer),
        ready_notes=list(DEMO_NOTES) if settings.DEMO_SEED else [],
    )


def people_named(flags: Sequence[Flag]) -> dict[uuid.UUID, dict[uuid.UUID, str]]:
    """Those each flag names, each job's id with its nickname, in the order it names them, by the flag's id: the tap's
    worker first, then whoever made the record before it (ATT-1)."""
    names: dict[uuid.UUID, dict[uuid.UUID, str]] = defaultdict(dict)
    # Through the link rows' own guard, which leads with the shop, as their index does, not through Flag.people, whose
    # query would name no shop. Their ids are UUIDv7s, so in the order raise_flag wrote them.
    for person in FlagPerson.objects.filter(flag__in=flags).select_related("staff").order_by("id"):
        names[person.flag_id][person.staff_id] = person.staff.display_name
    return names


def _records(flags: Sequence[Flag]) -> dict[uuid.UUID, CounterRecord]:
    # The counter records the flags are about, by id: a tap, a pushed record's line. A flag about a row no laptop made
    # has none here, and its line shows the flag's own facts alone.
    wanted: dict[str, set[uuid.UUID]] = defaultdict(set)
    for flag in flags:
        wanted[flag.subject_type].add(flag.subject_id)
    records: dict[uuid.UUID, CounterRecord] = {}
    for code, ids in wanted.items():
        table = table_of(code)
        if issubclass(table, CounterRecord):
            rows: models.QuerySet[Any] = table._default_manager.filter(pk__in=ids).select_related("device")
            records.update((row.pk, row) for row in rows)
    return records
