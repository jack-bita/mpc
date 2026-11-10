"""apps/sync/tests/test_push.py — saving a batch of documents a laptop pushed (apps/sync/push.py; SYNC-4, 03 §6.3).

The Dawa laptop worked offline all morning and sends what it saved, #1, #2, #3. For each one, in its number's order,
the push answers:

    accepted    saved: its document, its change lines and its line in the receipt book, in one transaction
    duplicate   saved before: the first answer again, and nothing saved twice
    invalid     can't be saved: set aside, with its reason and a flag, and the others go on
    retry       a server problem: nothing of it saved, and the batch stops there, to keep the order

These tests send pretend "ticket" documents, which save a test-only Ticket (tests/probe/documents.py), through the
service itself; the route around it, with the laptop's key, is test_push_route.py's. Fake data only: the repo is public.
"""

import dataclasses
import datetime as dt
import uuid
from collections.abc import Sequence
from typing import Any

import pytest
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Model

from apps.control.models import EditEvent, Flag, FlagKind, FlagPerson
from apps.core.links import LINK_TYPES
from apps.core.tenancy import shop_context
from apps.people.models import Device, StaffMember
from apps.shops.models import Shop, Side
from apps.sync import push as push_module
from apps.sync.document_types import DOCUMENT_TYPES, Document
from apps.sync.models import PushedDocument, PushedStatus
from apps.sync.push import Answer, Sent, push
from tests.change_log import last_line, lines_written
from tests.concurrency import in_another_transaction, wait_until_someone_waits_for_me
from tests.probe.documents import TICKET, TICKET_CODE, post_ticket
from tests.probe.models import Card, Ticket

pytestmark = pytest.mark.django_db

# Asha served the customer at 10:42 by the laptop's clock; the push reached the server at 14:05. Both in UTC (03 §6.6).
CLIENT_TIME = dt.datetime(2026, 11, 10, 7, 42, tzinfo=dt.UTC)
RECEIVED_AT = dt.datetime(2026, 11, 10, 11, 5, tzinfo=dt.UTC)


@pytest.fixture(autouse=True)
def ticket_type(monkeypatch: pytest.MonkeyPatch) -> None:
    # The pretend ticket on the list of document types, and its table's link type code, for as long as each test runs.
    monkeypatch.setitem(DOCUMENT_TYPES, ("ticket", 1), TICKET)
    monkeypatch.setitem(LINK_TYPES, TICKET_CODE, "probe.Ticket")


@pytest.fixture
def device_b(shop_b: Shop, side_b: Side) -> Device:
    # A laptop of the second shop. Only the row, as device_a is (backend/conftest.py).
    with shop_context(shop_b):
        return Device.objects.create(shop=shop_b, home_side=side_b, name="Laptop B", code=1, key_hash="b" * 64)


def _sent(device_seq: int, maker: StaffMember, *, text: str = "2 bags of pumba", **more: Any) -> Sent:
    # One ticket as the laptop sent it, its number `device_seq`, made by `maker`; `more` adds to its payload, or
    # overrides the envelope (`type`, `schema_version`, `id`).
    envelope = {key: more.pop(key) for key in ("type", "schema_version", "id") if key in more}
    return Sent(
        id=envelope.get("id", uuid.uuid7()),
        type=envelope.get("type", "ticket"),
        schema_version=envelope.get("schema_version", 1),
        device_seq=device_seq,
        client_time=CLIENT_TIME,
        created_by=maker.pk,
        payload={"text": text, **more},
    )


def _push(device: Device, documents: Sequence[Sent]) -> list[Answer]:
    # The push as the route runs it: inside the laptop's shop, which its key opened.
    with shop_context(device.shop_id):
        return push(device, documents, received_at=RECEIVED_AT)


def _again(answer: Answer) -> Answer:
    # What the same document gets when it is sent again: "duplicate", with the first answer.
    return dataclasses.replace(answer, status="duplicate", first=answer.status)


def _tickets(shop: Model) -> list[tuple[int, str]]:
    # The shop's saved tickets, by their laptop number: what was really saved, and in which order it was made.
    with shop_context(shop):
        return list(Ticket.objects.order_by("device_seq").values_list("device_seq", "text"))


def _flags(shop: Model, kind: FlagKind) -> list[Flag]:
    with shop_context(shop):
        return list(Flag.objects.filter(kind=kind))


def _named(flag: Flag) -> list[uuid.UUID]:
    # The staff members a flag names, read inside its shop.
    return list(FlagPerson.objects.filter(flag=flag).values_list("staff_id", flat=True))


def test_same_batch_twice_posts_once(shop_a: Model, device_a: Device, staff_a: StaffMember) -> None:
    # The laptop sent #1 and #2, the server saved both, and the answer was lost on the way back. The laptop sends the
    # same batch again: nothing is saved twice, no line is written twice, and each document gets its first answer.
    batch = [_sent(1, staff_a), _sent(2, staff_a, broke=FlagKind.NEGATIVE_STOCK)]
    first = _push(device_a, batch)
    with lines_written(shop_a) as lines:
        again = _push(device_a, batch)
    assert [answer.status for answer in first] == ["accepted", "accepted"]
    assert again == [_again(answer) for answer in first]
    assert lines == []
    assert _tickets(shop_a) == [(1, "2 bags of pumba"), (2, "2 bags of pumba")]
    assert len(_flags(shop_a, FlagKind.NEGATIVE_STOCK)) == 1


def test_posts_in_device_seq_order(shop_a: Model, device_a: Device, staff_a: StaffMember) -> None:
    # The batch arrives out of order, #3, #1, #2: #3 could be a repayment of the debt #2 made. Each is saved, and
    # answered, in the order the laptop made them, so their change numbers follow that order too.
    third, first, second = _sent(3, staff_a), _sent(1, staff_a), _sent(2, staff_a)
    with lines_written(shop_a) as lines:
        answers = _push(device_a, [third, first, second])
    assert [answer.id for answer in answers] == [first.id, second.id, third.id]
    assert [record for _code, record, _op in lines] == [first.id, second.id, third.id]
    # Each took a change number, and a later one than the document before it.
    posted = [answer.posted_seq or 0 for answer in answers]
    assert 0 < posted[0] < posted[1] < posted[2]


def test_invalid_document_flagged_and_skipped(shop_a: Model, device_a: Device, staff_a: StaffMember) -> None:
    # #2's text is too long for its shape. It is set aside with its reason, and one flag about its line names who made
    # it; #1 and #3 are saved. Sent again, #2 gets the same answer, and no second flag.
    batch = [_sent(1, staff_a), _sent(2, staff_a, text="x" * 101), _sent(3, staff_a)]
    answers = _push(device_a, batch)
    assert [answer.status for answer in answers] == ["accepted", "invalid", "accepted"]
    assert answers[1] == Answer(id=batch[1].id, status="invalid", code="invalid", fields={"text": ["max_length"]})
    assert [seq for seq, _text in _tickets(shop_a)] == [1, 3]
    (flag,) = _flags(shop_a, FlagKind.INVALID_DOCUMENT)
    with shop_context(shop_a):
        line = PushedDocument.objects.get(document_id=batch[1].id)
        assert (flag.subject, _named(flag)) == (line, [staff_a.pk])
    assert _push(device_a, batch)[1] == _again(answers[1])
    assert len(_flags(shop_a, FlagKind.INVALID_DOCUMENT)) == 1


def test_unknown_type_is_invalid(shop_a: Model, device_a: Device, staff_a: StaffMember) -> None:
    # A type the server doesn't take offline: refused with the list's own code, and kept, as sent, in its line.
    sent = _sent(1, staff_a, type="receipt")
    assert _push(device_a, [sent]) == [Answer(id=sent.id, status="invalid", code="document.type_unknown")]
    with shop_context(shop_a):
        assert PushedDocument.objects.get().type == "receipt"


def test_uuid_from_other_shop_rejected_silently(
    shop_a: Model, shop_b: Model, device_a: Device, device_b: Device, staff_a: StaffMember, staff_b: StaffMember
) -> None:
    # Shop B's laptop sends a document with the id of a ticket shop A already saved. B can't see A's rows, so the id
    # looks new until the insert clashes; the answer says only that the id can't be used, nothing of A's ticket, not
    # even that it is a ticket (03 §5.4, CORE-6). A's ticket is untouched; B keeps its own line and its own flag.
    taken = _sent(1, staff_a)
    _push(device_a, [taken])
    copy = _sent(1, staff_b, text="something else", id=taken.id)
    assert _push(device_b, [copy]) == [Answer(id=taken.id, status="invalid", code="id.taken")]
    assert _tickets(shop_a) == [(1, "2 bags of pumba")]
    assert _tickets(shop_b) == []
    assert len(_flags(shop_b, FlagKind.INVALID_DOCUMENT)) == 1
    assert _flags(shop_a, FlagKind.INVALID_DOCUMENT) == []


def test_server_error_answers_retry(
    monkeypatch: pytest.MonkeyPatch, shop_a: Model, device_a: Device, staff_a: StaffMember
) -> None:
    # #2 hits a server problem, a bug or a lost database, not a problem of the document. Nothing of #2 is saved, and
    # the batch stops there: #3 gets no answer, as it might rest on #2. Once the server is fixed, the laptop sends #2
    # and #3 again and both go in; #1 is a duplicate.
    def crash_on_two(document: Document, payload: dict[str, Any]) -> list[Flag]:
        if document.device_seq == 2:
            raise RuntimeError("the server broke")
        return post_ticket(document, payload)

    monkeypatch.setitem(DOCUMENT_TYPES, ("ticket", 1), dataclasses.replace(TICKET, post=crash_on_two))
    batch = [_sent(1, staff_a), _sent(2, staff_a), _sent(3, staff_a)]
    answers = _push(device_a, batch)
    assert [answer.status for answer in answers] == ["accepted", "retry"]
    assert answers[1] == Answer(id=batch[1].id, status="retry")
    assert _tickets(shop_a) == [(1, "2 bags of pumba")]
    with shop_context(shop_a):
        assert not PushedDocument.objects.filter(document_id__in=[batch[1].id, batch[2].id]).exists()

    monkeypatch.setitem(DOCUMENT_TYPES, ("ticket", 1), TICKET)
    assert [answer.status for answer in _push(device_a, batch)] == ["duplicate", "accepted", "accepted"]
    assert [seq for seq, _text in _tickets(shop_a)] == [1, 2, 3]


def test_a_document_and_its_answer_line_are_saved_in_one_transaction(
    monkeypatch: pytest.MonkeyPatch, shop_a: Model, device_a: Device, staff_a: StaffMember
) -> None:
    # The ticket is saved, then its line in the answer log can't be: the server stops between the two. Had the ticket
    # stayed alone, the laptop's resend would find no line, clash on the ticket's id, and answer `id.taken`: a sale that
    # really went in, set aside under "needs attention". So the two go together: the ticket and its change lines roll
    # back, and the answer is `retry`, as for any server problem.
    real_line = push_module._line

    def a_line_the_database_refuses(*args: Any, **answer: Any) -> PushedDocument:
        line = real_line(*args, **answer)
        line.reason = "never.saved"  # an accepted line with a reason: sync_pusheddocument_accepted_has_no_reason
        return line

    monkeypatch.setattr(push_module, "_line", a_line_the_database_refuses)
    sent = _sent(1, staff_a)
    with lines_written(shop_a) as lines:
        assert _push(device_a, [sent]) == [Answer(id=sent.id, status="retry")]
    assert _tickets(shop_a) == []
    assert lines == []


def test_an_invalid_line_and_its_flag_are_saved_together(
    monkeypatch: pytest.MonkeyPatch, shop_a: Model, device_a: Device, staff_a: StaffMember
) -> None:
    # An invalid document's line is written, then its flag can't be. Had the line stayed alone, every resend would get
    # the stored `invalid` and no manager would ever see a flag for it. So the line goes too, and the answer is `retry`:
    # sent again, the document gets its line and its flag together.
    def no_flag(**_: Any) -> Flag:
        raise RuntimeError("the flag could not be raised")

    monkeypatch.setattr(push_module, "raise_flag", no_flag)
    sent = _sent(1, staff_a, type="receipt")
    assert _push(device_a, [sent]) == [Answer(id=sent.id, status="retry")]
    with shop_context(shop_a):
        assert not PushedDocument.objects.exists()


def test_accepted_answer_carries_its_change_number_and_flags(
    shop_a: Model, device_a: Device, staff_a: StaffMember
) -> None:
    # The sale broke a rule, and is saved with a flag (accept, then flag). Its answer names the flag, and the last
    # change number its save took: the laptop drops the sale's "still waiting" stock once its pull passes that number.
    sent = _sent(1, staff_a, broke=FlagKind.NEGATIVE_STOCK)
    with lines_written(shop_a) as lines:
        (answer,) = _push(device_a, [sent])
    (flag,) = _flags(shop_a, FlagKind.NEGATIVE_STOCK)
    assert lines == [(TICKET_CODE, sent.id, "upsert")]
    assert answer == Answer(
        id=sent.id,
        status="accepted",
        posted_seq=last_line(shop_a),
        flags=[{"id": str(flag.pk), "kind": "negative_stock"}],
    )


def test_maker_of_another_shop_is_invalid(shop_a: Model, device_a: Device, staff_b: StaffMember) -> None:
    # The document names, as its maker, someone who doesn't work at this shop: never saved under their name. The
    # answer says only that the maker is unknown here, and the line and its flag name nobody.
    sent = _sent(1, staff_b)
    assert _push(device_a, [sent]) == [Answer(id=sent.id, status="invalid", code="document.maker_unknown")]
    with shop_context(shop_a):
        assert PushedDocument.objects.get().created_by_id is None
    (flag,) = _flags(shop_a, FlagKind.INVALID_DOCUMENT)
    with shop_context(shop_a):
        assert _named(flag) == []


def test_document_records_who_made_it_its_laptop_and_both_clocks(
    shop_a: Model, device_a: Device, staff_a: StaffMember
) -> None:
    # X3: the saved ticket, and its line in the receipt book, name who made it at the counter and the laptop it came
    # from, with the laptop's number for it and both clocks: the laptop's, kept but not trusted, and the server's.
    _push(device_a, [_sent(12, staff_a)])
    facts = ("created_by_id", "device_id", "device_seq", "client_time", "received_at")
    expected = (staff_a.pk, device_a.pk, 12, CLIENT_TIME, RECEIVED_AT)
    with shop_context(shop_a):
        assert Ticket.objects.values_list(*facts).get() == expected
        line = PushedDocument.objects.get()
        assert tuple(getattr(line, fact) for fact in facts) == expected
        assert (line.type, line.schema_version, line.status) == ("ticket", 1, PushedStatus.ACCEPTED)


def _refusing(error: Exception) -> Any:
    # The pretend ticket's saving code, made to fail with `error` after it has saved its ticket, so the test also
    # proves that what it saved rolls back.
    def post(document: Document, payload: dict[str, Any]) -> list[Flag]:
        post_ticket(document, payload)
        raise error

    return dataclasses.replace(TICKET, post=post)


def test_a_refusal_of_the_saving_code_is_invalid(
    monkeypatch: pytest.MonkeyPatch, shop_a: Model, device_a: Device, staff_a: StaffMember
) -> None:
    # A document its saving code refuses outright, for what no flag can mend: set aside with the code's own reason,
    # and nothing it saved before refusing is kept.
    refusal = ValidationError("This ticket can't be saved.", code="ticket.cannot")
    monkeypatch.setitem(DOCUMENT_TYPES, ("ticket", 1), _refusing(refusal))
    sent = _sent(1, staff_a)
    assert _push(device_a, [sent]) == [Answer(id=sent.id, status="invalid", code="ticket.cannot")]
    assert _tickets(shop_a) == []


def _checked_first(document: Document, payload: dict[str, Any]) -> list[Flag]:
    # A saving code that checks its row before saving it (full_clean), as a service may: twice the pretend sale's text,
    # so a long one also breaks the text's own rule.
    shop_id = document.device.shop_id
    Ticket(
        id=document.id,
        shop_id=shop_id,
        device=document.device,
        device_seq=document.device_seq,
        client_time=document.client_time,
        received_at=document.received_at,
        text=payload["text"] * 2,
    ).full_clean()
    return post_ticket(document, payload)


@pytest.mark.parametrize(
    ("text", "answer"),
    [("2 bags", ("id.taken", {})), ("x" * 60, ("invalid", {"text": ["max_length"]}))],
    ids=["only_the_id", "and_the_text"],
)
def test_an_id_taken_in_this_shop_gets_the_same_answer_as_in_another(
    monkeypatch: pytest.MonkeyPatch,
    shop_a: Model,
    device_a: Device,
    staff_a: StaffMember,
    text: str,
    answer: tuple[str, dict[str, list[str]]],
) -> None:
    # A saving code's own check reads through the shop's guard (CORE-2): it finds an id taken by a row of this shop, a
    # row on a side the laptop's people can't see included, and calls it "unique", while another shop's row only the
    # insert finds, as `id.taken`. Two answers would tell a laptop which; so that "unique" is left out, as CORE-6's
    # create does: the rest is the answer, else the id is taken (03 §5.4).
    monkeypatch.setitem(DOCUMENT_TYPES, ("ticket", 1), dataclasses.replace(TICKET, post=_checked_first))
    taken = uuid.uuid7()
    Ticket(
        id=taken, shop_id=shop_a.pk, device=device_a, device_seq=9, client_time=CLIENT_TIME, received_at=RECEIVED_AT
    ).save()
    sent = _sent(1, staff_a, text=text, id=taken)
    code, fields = answer
    assert _push(device_a, [sent]) == [Answer(id=taken, status="invalid", code=code, fields=fields)]


def test_another_database_rule_answers_retry(shop_a: Model, device_a: Device, staff_a: StaffMember) -> None:
    # A clash on a rule other than an id the laptop made: here, a ticket this laptop already has under number 5, made
    # some other way, with no line in the answer log (one ticket per laptop number, tests/probe/models.py). The new
    # document's id is free, so no id is taken: it is a rule the saving code should have checked first, a bug on the
    # server, so a retry. `id.taken` would set a good sale aside for good.
    Ticket(
        shop_id=shop_a.pk,
        device=device_a,
        device_seq=5,
        client_time=CLIENT_TIME,
        received_at=RECEIVED_AT,
        text="made some other way",
    ).save()
    sent = _sent(5, staff_a)
    assert _push(device_a, [sent]) == [Answer(id=sent.id, status="retry")]
    assert _tickets(shop_a) == [(5, "made some other way")]


def test_a_pushed_documents_edits_name_its_maker_and_its_laptop(
    monkeypatch: pytest.MonkeyPatch, shop_a: Model, device_a: Device, staff_a: StaffMember
) -> None:
    # X3: every write records the person and the device. A sale Asha made on the Dawa laptop, saved hours later by the
    # push, changes an office record, as a sale will change a customer's balance: its edit history names Asha and the
    # laptop, not nobody, nor only the laptop the visit came from. The test-only Card keeps an edit history (its
    # migration's RecordEditsV2), and both books read the same note (apps/core/acting.py).
    card = Card(shop_id=shop_a.pk, name="Dawa")
    card.save()

    def rename_the_card(document: Document, payload: dict[str, Any]) -> list[Flag]:
        flags = post_ticket(document, payload)
        Card.objects.filter(pk=card.pk).update(name=payload["text"])
        return flags

    monkeypatch.setitem(DOCUMENT_TYPES, ("ticket", 1), dataclasses.replace(TICKET, post=rename_the_card))
    _push(device_a, [_sent(1, staff_a, text="Dawa za Mifugo")])
    with shop_context(shop_a):
        (edit,) = EditEvent.objects.filter(subject_type="probe_card", subject_id=card.pk)
    assert (edit.created_by_id, edit.device_id) == (staff_a.pk, device_a.pk)
    assert edit.after == {"name": "Dawa za Mifugo"}


def _with_its_own_id(document: Document, payload: dict[str, Any]) -> list[Flag]:
    # The pretend ticket saved under an id the server makes, not the document's: a twin's ticket then never clashes on
    # the id, only on the rule of one ticket per laptop number, as a sale's receipt number will.
    return post_ticket(dataclasses.replace(document, id=uuid.uuid7()), payload)


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    ("text", "clashes_on"),
    [("2 bags of pumba", "the id"), ("x" * 101, "the line"), ("2 bags of pumba", "another rule")],
    ids=["accepted", "invalid", "another_rule"],
)
def test_twin_sent_at_the_same_moment_answers_duplicate(
    monkeypatch: pytest.MonkeyPatch, shop_a: Model, device_a: Device, staff_a: StaffMember, text: str, clashes_on: str
) -> None:
    # Two copies of one batch at the same moment: the laptop sent again while the first was still being saved. The
    # second copy finds no line yet, so it starts saving too, and waits on the first copy's rows; once the first
    # commits, its insert clashes: on the ticket's id, on the invalid document's line, or on another rule of the saving
    # code's tables. Whichever it is, it looks in the answer log again, finds the first copy's line, and answers with
    # that: one ticket, one flag at most, and both copies get the first answer (CORE-6).
    if clashes_on == "another rule":
        monkeypatch.setitem(DOCUMENT_TYPES, ("ticket", 1), dataclasses.replace(TICKET, post=_with_its_own_id))
    sent = _sent(1, staff_a, text=text)
    with shop_context(shop_a), transaction.atomic():
        (first,) = push(device_a, [sent], received_at=RECEIVED_AT)
        twin, ended = in_another_transaction(lambda: _push(device_a, [sent]))
        wait_until_someone_waits_for_me()
    twin.join()
    assert ended == [[_again(first)]]
    assert len(_tickets(shop_a)) == (first.status == "accepted")
    assert len(_flags(shop_a, FlagKind.INVALID_DOCUMENT)) == (first.status == "invalid")
