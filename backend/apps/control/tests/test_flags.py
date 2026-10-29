"""apps/control/tests/test_flags.py — tests for flags: one review queue for every difference (02 §13).

E4's cash-up, as a flag:

    kind             subject             expected   actual    difference  people  side  status
    cash_difference  the Dawa drawer's   163,000    160,000   −3,000      Asha    Dawa  open
                     day

It then moves forward only, and every step is a note with who, when and why (Jack, 29 Oct 2026; 02 v1.8):

    open ──explain──▶ explained ──resolve / dismiss──▶ resolved | dismissed   (final)
      └───────────────resolve / dismiss─────────────────▶

The tables a real flag is about (a drawer's day, a stock count, a sale) come with later cards, so the
test-only probe Note stands in for them, with a type code of its own for the length of each test
(apps/core/links.py). `control` may not import `shops` or `people` (ADR-0035), not even in its tests, so
the shops, sides and staff come from backend/conftest.py, typed by what they are to `control`: a shop's row,
or an Actor. Fake data only: the repo is public (03 §10).
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.models import Model
from pytest_django import DjangoAssertNumQueries

from apps.control.models import Flag, FlagKind, FlagNote, FlagPerson, FlagStatus, FlagStep
from apps.control.services import dismiss_flag, explain_flag, raise_flag, resolve_flag
from apps.core.links import LINK_TYPES
from apps.core.models import AppendOnlyError, ShopScoped
from apps.core.tenancy import Actor, ShopMismatch, shop_context
from tests.probe.models import Note

pytestmark = pytest.mark.django_db

# E4 (02 §18): the drawer should hold 163,000, and 160,000 is counted. Money is a Decimal, never a float
# (ADR-0024).
EXPECTED_CASH = Decimal("163000.00")
COUNTED_CASH = Decimal("160000.00")


@dataclass(frozen=True)
class DeviceAlone:
    # An Actor that is no person: a paired device acting by itself (03 §5.4), so its staff_id is None.
    shop_id: uuid.UUID
    staff_id: uuid.UUID | None = None


@pytest.fixture(autouse=True)
def note_has_a_code(monkeypatch: pytest.MonkeyPatch) -> None:
    # monkeypatch puts the list back as it was after each test, so the code never reaches the real list.
    monkeypatch.setitem(LINK_TYPES, "probe_note", "probe.Note")


@pytest.fixture
def drawer_day(shop_a: Model) -> Note:
    # Stands in for the Dawa drawer's day (CASH-2's DrawerSession, still to come).
    note = Note(shop_id=shop_a.pk, text="Droo ya Dawa, 28 Oct")
    note.save()
    return note


@pytest.fixture
def flag(shop_a: Model, drawer_day: Note, side_a: ShopScoped, staff_a: Actor) -> Flag:
    # E4's flag, raised by the system as the cash-up is posted: nobody acts, so `by` is None.
    with shop_context(shop_a):
        return raise_flag(
            kind=FlagKind.CASH_DIFFERENCE,
            subject=drawer_day,
            expected=EXPECTED_CASH,
            actual=COUNTED_CASH,
            side=side_a,
            people=[staff_a],
            by=None,
        )


def notes_of(flag: Flag) -> list[tuple[str, str, uuid.UUID | None]]:
    # A flag's notes in the order they were written: the step, the words and who wrote them.
    rows = FlagNote.objects.filter(flag=flag).order_by("created_at", "id")
    return [(note.step, note.text, note.created_by_id) for note in rows]


def test_raise_flag_records_subject_and_people(
    shop_a: Model, drawer_day: Note, side_a: ShopScoped, staff_a: Actor
) -> None:
    with shop_context(shop_a):
        # Asha named twice, as a raiser might when she took two payments in the window: she is named once.
        raised = raise_flag(
            kind=FlagKind.CASH_DIFFERENCE,
            subject=drawer_day,
            expected=EXPECTED_CASH,
            actual=COUNTED_CASH,
            side=side_a,
            people=[staff_a, staff_a],
            by=None,
        )
        stored = Flag.objects.get(pk=raised.pk)
        people = [person.pk for person in stored.people.all()]

    assert stored.kind == FlagKind.CASH_DIFFERENCE
    # The subject is two columns: which table, by its code, and which row.
    assert (stored.subject_type, stored.subject_id) == ("probe_note", drawer_day.pk)
    assert (stored.expected, stored.actual) == (EXPECTED_CASH, COUNTED_CASH)
    # The database works the difference out itself, so it can never disagree with the two numbers. The flag
    # raise_flag hands back has it too: Django reads it back as the row is saved.
    assert stored.difference == raised.difference == Decimal("-3000")
    assert stored.side_id == side_a.pk
    assert people == [staff_a.staff_id]
    assert stored.status == FlagStatus.OPEN
    assert stored.created_by_id is None


def test_flag_subject_loads_from_its_type_code_and_uuid(shop_a: Model, flag: Flag, drawer_day: Note) -> None:
    with shop_context(shop_a):
        stored = Flag.objects.get(pk=flag.pk)
        # Loaded through the shop guard, from the two columns alone (apps/core/links.py).
        assert stored.subject == drawer_day


# Both ways to close a flag, each with the status it leaves and a note in the shop's words: a real difference
# dealt with, or none after all. Every rule about closing holds for both, so each test below runs once with each.
CLOSES = [
    pytest.param(resolve_flag, FlagStatus.RESOLVED, "Atalipa 3,000 kesho", id="resolve"),
    pytest.param(dismiss_flag, FlagStatus.DISMISSED, "Pesa ilipatikana chini ya droo", id="dismiss"),
]


@pytest.mark.parametrize(("close", "closed_status", "words"), CLOSES)
def test_flag_status_only_moves_forward(
    shop_a: Model,
    flag: Flag,
    staff_a: Actor,
    staff_a2: Actor,
    close: Callable[..., Flag],
    closed_status: FlagStatus,
    words: str,
) -> None:
    with shop_context(shop_a):
        explained = explain_flag(flag, note="Nilitoa chenji zaidi", by=staff_a)
        assert explained.status == FlagStatus.EXPLAINED
        closed = close(explained, note=words, by=staff_a2)
        assert closed.status == closed_status

        # Closed is final: no more notes, whatever the step. Each move is tried with `flag`, the copy read
        # before any of this, which still says open, as a second manager's screen would: the service reads
        # the row again, locked, and sees it is closed.
        for move in (explain_flag, resolve_flag, dismiss_flag):
            with pytest.raises(ValidationError) as refused:
                move(flag, note="Tena", by=staff_a2)
            assert refused.value.code == "flag.closed"

        assert Flag.objects.get(pk=flag.pk).status == closed_status
        assert [step for step, _, _ in notes_of(flag)] == [FlagStep.EXPLAINED, closed_status]


@pytest.mark.parametrize(("close", "closed_status", "words"), CLOSES)
def test_flag_closes_without_explanation(
    shop_a: Model, flag: Flag, staff_a2: Actor, close: Callable[..., Flag], closed_status: FlagStatus, words: str
) -> None:
    # A manager who finds the reason may close the flag straight from open, with their own note (Jack,
    # 29 Oct 2026): settled by them, or found to be no problem at all.
    with shop_context(shop_a):
        closed = close(flag, note=words, by=staff_a2)

        assert closed.status == closed_status
        assert notes_of(flag) == [(closed_status, words, staff_a2.staff_id)]


@pytest.mark.parametrize(("close", "closed_status", "words"), CLOSES)
def test_named_person_cannot_close_their_own_flag(
    shop_a: Model,
    flag: Flag,
    staff_a: Actor,
    staff_a2: Actor,
    close: Callable[..., Flag],
    closed_status: FlagStatus,
    words: str,
) -> None:
    # E4's flag names Asha. She may say why her drawer is short, but not decide it: closing it herself, with
    # "no problem", would hide her own shortage from the owner (Jack, at CTRL-1's review; 02 v1.8).
    with shop_context(shop_a):
        explain_flag(flag, note="Nilitoa chenji zaidi", by=staff_a)
        with pytest.raises(ValidationError) as refused:
            close(flag, note=words, by=staff_a)
        assert refused.value.code == "flag.own_flag"
        assert Flag.objects.get(pk=flag.pk).status == FlagStatus.EXPLAINED

        # Someone the flag doesn't name decides it.
        assert close(flag, note=words, by=staff_a2).status == closed_status


def test_every_explanation_is_kept(shop_a: Model, side_a: ShopScoped, staff_a: Actor, staff_a2: Actor) -> None:
    # E9 (02 §18): a 50 kg bag, and only 48.5 kg sold loose before the next was opened. Both sellers sold
    # loose kg in that window, so the flag names both, and each explains (Jack, 29 Oct 2026).
    bag = Note(shop_id=shop_a.pk, text="Mfuko wa pumba, 28 Oct")
    bag.save()
    with shop_context(shop_a):
        raised = raise_flag(
            kind=FlagKind.OPEN_BAG_DIFFERENCE,
            subject=bag,
            expected=Decimal("50.000"),
            actual=Decimal("48.500"),
            side=side_a,
            people=[staff_a, staff_a2],
            by=None,
        )
        explain_flag(raised, note="Nilipima kwa mzani wa zamani", by=staff_a)
        explained = explain_flag(raised, note="Mteja alimwaga kidogo", by=staff_a2)

        assert raised.difference == Decimal("-1.5")
        # A second explanation keeps the status, and replaces nothing.
        assert explained.status == FlagStatus.EXPLAINED
        assert notes_of(raised) == [
            (FlagStep.EXPLAINED, "Nilipima kwa mzani wa zamani", staff_a.staff_id),
            (FlagStep.EXPLAINED, "Mteja alimwaga kidogo", staff_a2.staff_id),
        ]


def test_unknown_flag_kind_refused(shop_a: Model, drawer_day: Note) -> None:
    # One list of kinds (02 §13), so the review screen (CTRL-4) never meets a kind it can't show or filter.
    with shop_context(shop_a):
        with pytest.raises(ValidationError) as refused:
            raise_flag(kind="cash_shortage", subject=drawer_day, by=None)  # type: ignore[arg-type]
        assert [error.code for error in refused.value.error_dict["kind"]] == ["invalid_choice"]
        assert not Flag.objects.exists()

    # The database refuses one too, even from code that skips the service and every check.
    unknown = Flag(shop_id=shop_a.pk, kind="cash_shortage", subject_type="probe_note", subject_id=drawer_day.pk)
    with pytest.raises(IntegrityError, match="control_flag_kind_known"), transaction.atomic():
        unknown.save()


def test_flag_numbers_come_in_pairs(shop_a: Model, drawer_day: Note) -> None:
    # A difference needs both numbers. One alone would show a flag with a difference of nothing.
    with shop_context(shop_a):
        for expected, actual in [(EXPECTED_CASH, None), (None, COUNTED_CASH)]:
            with pytest.raises(ValidationError) as refused:
                raise_flag(kind=FlagKind.CASH_DIFFERENCE, subject=drawer_day, expected=expected, actual=actual, by=None)
            assert [error.code for error in refused.value.error_dict["__all__"]] == ["flag.numbers_unpaired"]

        # Some kinds have no numbers at all: a transaction code used twice is a fact, not an amount.
        duplicate = raise_flag(kind=FlagKind.DUPLICATE_CODE, subject=drawer_day, by=None)
        assert (duplicate.expected, duplicate.actual, duplicate.difference) == (None, None, None)


@pytest.mark.parametrize(
    ("rule", "bad_row"),
    [
        # A note of nothing: the services trim and refuse it first (flag.note_required).
        (
            "control_flagnote_text_not_blank",
            lambda flag, person: FlagNote(shop_id=flag.shop_id, flag=flag, step="explained", text=""),
        ),
        # A note that opens a flag: no step does that, only raise_flag.
        (
            "control_flagnote_step_known",
            lambda flag, person: FlagNote(shop_id=flag.shop_id, flag=flag, step="open", text="Tena"),
        ),
        # Asha named twice on one flag: raise_flag names each person once.
        (
            "control_flagperson_once",
            lambda flag, person: FlagPerson(shop_id=flag.shop_id, flag=flag, staff_id=person.staff_id),
        ),
        # A status no screen knows: the services only ever set the four.
        (
            "control_flag_status_known",
            lambda flag, person: Flag(
                shop_id=flag.shop_id,
                kind=flag.kind,
                subject_type="probe_note",
                subject_id=flag.subject_id,
                status="closed",
            ),
        ),
        # A table's code with a capital and a space: link_type_of hands out codes from the list only.
        (
            "control_flag_subject_type_shape",
            lambda flag, person: Flag(
                shop_id=flag.shop_id, kind=flag.kind, subject_type="Probe Note", subject_id=flag.subject_id
            ),
        ),
    ],
    ids=["blank_note", "note_that_opens", "person_twice", "unknown_status", "bad_type_code"],
)
def test_database_refuses_what_the_services_check_first(
    flag: Flag, staff_a: Actor, rule: str, bad_row: Callable[[Flag, Actor], Model]
) -> None:
    # The services refuse each of these before the database is asked, so no other test reaches the database's
    # own rule: dropped from the migration, it would leave every test green. Here the row is saved directly, as a
    # bug or SQL typed by hand would, past the service and every check: the database is the last guard (03 §5.6).
    with pytest.raises(IntegrityError, match=rule), transaction.atomic():
        bad_row(flag, staff_a).save()


def test_flag_links_stay_in_one_shop(
    shop_a: Model,
    shop_b: Model,
    drawer_day: Note,
    flag: Flag,
    side_b: ShopScoped,
    staff_a: Actor,
    staff_b: Actor,
) -> None:
    # T1: a flag, and every row it links to, belong to one shop. Each of these is a bug in the calling
    # code, refused before anything is written.
    with shop_context(shop_a):
        # Shop B's side, shop B's seller, and shop B's staff member acting.
        with pytest.raises(ShopMismatch):
            raise_flag(kind=FlagKind.CASH_DIFFERENCE, subject=drawer_day, side=side_b, by=None)
        with pytest.raises(ShopMismatch):
            raise_flag(kind=FlagKind.CASH_DIFFERENCE, subject=drawer_day, people=[staff_b], by=None)
        with pytest.raises(ShopMismatch):
            raise_flag(kind=FlagKind.CASH_DIFFERENCE, subject=drawer_day, by=staff_b)
        # A moved flag stays in its shop too: shop B's staff can't explain shop A's flag.
        with pytest.raises(ShopMismatch):
            explain_flag(flag, note="Si mimi", by=staff_b)
    # Shop B's visit can't flag shop A's row, nor move shop A's flag.
    with shop_context(shop_b):
        with pytest.raises(ShopMismatch):
            raise_flag(kind=FlagKind.CASH_DIFFERENCE, subject=drawer_day, by=None)
        with pytest.raises(ShopMismatch):
            dismiss_flag(flag, note="Si tatizo", by=staff_b)

    with shop_context(shop_a):
        # A generic link has no foreign key, so the database can't check it: a row never saved would leave
        # the flag pointing at nothing.
        with pytest.raises(ValueError, match="saved"):
            raise_flag(kind=FlagKind.CASH_DIFFERENCE, subject=Note(shop_id=shop_a.pk, text="Bado"), by=None)
        # A flag names people: a device alone is no person.
        with pytest.raises(ValueError, match="person"):
            raise_flag(kind=FlagKind.CASH_DIFFERENCE, subject=drawer_day, people=[DeviceAlone(shop_a.pk)], by=None)

        # Only E4's flag, from the fixture: every refusal above wrote nothing, and moved nothing.
        assert list(Flag.objects.values_list("pk", "status")) == [(flag.pk, FlagStatus.OPEN)]
        assert notes_of(flag) == []


def test_flag_note_required(shop_a: Model, flag: Flag, staff_a: Actor) -> None:
    # Rule 7: every step keeps who, when and why. A note of only spaces says no more than none.
    with shop_context(shop_a):
        for move in (explain_flag, resolve_flag, dismiss_flag):
            for note in ["", "   "]:
                with pytest.raises(ValidationError) as refused:
                    move(flag, note=note, by=staff_a)
                assert refused.value.code == "flag.note_required"

        assert Flag.objects.get(pk=flag.pk).status == FlagStatus.OPEN
        assert notes_of(flag) == []


def test_every_step_names_its_person(shop_a: Model, flag: Flag) -> None:
    # Rule 7: every step keeps who. A note can never be edited (ADR-0021), so one saved without a name would
    # stay nameless for good. Whoever explains or closes a flag is a person: a device alone has nobody to
    # name (03 §5.4), and "nobody" is not an Actor at all, which the type checker refuses.
    device = DeviceAlone(shop_a.pk)
    with shop_context(shop_a):
        for move in (explain_flag, resolve_flag, dismiss_flag):
            with pytest.raises(ValueError, match="person"):
                move(flag, note="Imekaguliwa", by=device)

        assert Flag.objects.get(pk=flag.pk).status == FlagStatus.OPEN
        assert notes_of(flag) == []


def test_a_retried_step_is_written_once(
    shop_a: Model, flag: Flag, drawer_day: Note, staff_a: Actor, staff_a2: Actor
) -> None:
    # The phone makes each note's id, as it makes every record's (ADR-0007). A double tap, or a request sent
    # again after the network dropped, carries the same id: it gets the same answer, and no second note, which
    # could never be deleted (03 §5.5).
    explanation_id, close_id = uuid.uuid7(), uuid.uuid7()
    with shop_context(shop_a):
        explain_flag(flag, note="Nilitoa chenji zaidi", by=staff_a, note_id=explanation_id)
        again = explain_flag(flag, note="Nilitoa chenji zaidi", by=staff_a, note_id=explanation_id)
        assert again.status == FlagStatus.EXPLAINED

        resolve_flag(flag, note="Atalipa 3,000 kesho", by=staff_a2, note_id=close_id)
        # Sent again after it went through: the closed flag, as the first time, not "this flag is closed".
        resolved_again = resolve_flag(flag, note="Atalipa 3,000 kesho", by=staff_a2, note_id=close_id)
        assert resolved_again.status == FlagStatus.RESOLVED

        assert [step for step, _, _ in notes_of(flag)] == [FlagStep.EXPLAINED, FlagStep.RESOLVED]

        # An id that is already another flag's note is not a retry of this step: refused, as a create with a
        # taken id is (CORE-6).
        other = raise_flag(kind=FlagKind.DUPLICATE_CODE, subject=drawer_day, by=None)
        with pytest.raises(ValidationError) as refused:
            explain_flag(other, note="Nambari ilitumika mara mbili", by=staff_a, note_id=explanation_id)
        assert refused.value.code == "id.taken"
        assert notes_of(other) == []


def test_a_step_checks_only_what_it_changes(
    shop_a: Model, flag: Flag, staff_a: Actor, django_assert_max_num_queries: DjangoAssertNumQueries
) -> None:
    # A step writes one note and changes one column, the status. The flag's other fields were checked when
    # it was raised, and the trigger keeps them as they were (apps/control/operations.py), so checking them
    # all again cost a dozen queries a step, on a list a manager may close a page at a time (CTRL-4). The
    # limit leaves no room for that. 18 = the step's transaction (2) and the lock (1); the new note's own
    # checks, its links, its id and its two rules (10), and its insert (1); the status's one rule (3) and
    # its update (1). Re-checking the whole flag took it to 29.
    with shop_context(shop_a), django_assert_max_num_queries(18):
        explain_flag(flag, note="Nilitoa chenji zaidi", by=staff_a)


def test_flag_notes_cannot_be_edited(shop_a: Model, flag: Flag, staff_a: Actor) -> None:
    # Asha's words stay as she wrote them (Jack, 29 Oct 2026): FlagNote is append-only, in Python and in
    # PostgreSQL (ADR-0021).
    with shop_context(shop_a):
        explain_flag(flag, note="Nilitoa chenji zaidi", by=staff_a)
        note = FlagNote.objects.get(flag=flag)

    note.text = "Sikukosea"
    with pytest.raises(AppendOnlyError):
        note.save()
    with pytest.raises(AppendOnlyError):
        note.delete()
    # Plain SQL, which no model code sees: only the trigger is left to refuse it. (The table's name comes from
    # the model, not from outside, so building the SQL with it is safe; the values are parameters.)
    table = FlagNote._meta.db_table
    with pytest.raises(IntegrityError, match="append-only"), transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(f"UPDATE {table} SET text = %s WHERE id = %s", ["Sikukosea", note.pk])
    with pytest.raises(IntegrityError, match="append-only"), transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(f"DELETE FROM {table} WHERE id = %s", [note.pk])

    note.refresh_from_db()
    assert note.text == "Nilitoa chenji zaidi"


def test_flag_people_cannot_be_changed(shop_a: Model, flag: Flag, staff_a: Actor) -> None:
    # Who a flag names is part of the fact: E4's flag names Asha. Django's `flag.people.clear()`, `remove()`
    # and `set()` would delete the link rows with no who, when or why, and PROTECT doesn't stop them. So
    # FlagPerson is append-only too, in Python and in PostgreSQL (ADR-0021).
    with shop_context(shop_a):
        link = FlagPerson.objects.get(flag=flag)
        with pytest.raises(IntegrityError, match="append-only"), transaction.atomic():
            flag.people.clear()
        with pytest.raises(IntegrityError, match="append-only"), transaction.atomic():
            FlagPerson.objects.filter(pk=link.pk).update(staff_id=None)

        with pytest.raises(AppendOnlyError):
            link.save()
        with pytest.raises(AppendOnlyError):
            link.delete()

        assert [person.pk for person in flag.people.all()] == [staff_a.staff_id]
