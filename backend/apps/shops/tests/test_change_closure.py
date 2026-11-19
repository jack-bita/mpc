"""apps/shops/tests/test_change_closure.py — cancel_closure and change_last_day, the two ways a closure changes (ATT-8).

Each needs a reason, and writes both books: the audit trail keeps who, when and why (02 §13), and the edit history
keeps the field as it was and as it is, naming who (ADR-0036). Neither ever changes a day before today, so a day the
attendance may already have worked out and paid (ATT-10) stays as it was. Today is day 0 below:

    Ondoa (cancel), only up to its first day
        days 3–5                  → cancelled
        days 0–2                  → cancelled: it starts today, and today is still open
        days -1–2                 → closure.started: yesterday was already closed; move the last day instead

    the last day moved, earlier or later
        days -2–2   → day -1      → saved: the shop is open again from today
        days -3–2   → day -2      → closure.date_past: day -1, already past, would open again
        days -3–-1  → day 1       → saved: it ended yesterday, so it grows from today on
        days -5–-3  → day 1       → closure.date_past: days -2 and -1, already past, would close
        days 1–2    → day 4       → closure.overlaps, when another closure has day 4

On the demo, a person's change touches only days from tomorrow on (demo.closures_from_tomorrow).
"""

from datetime import date, timedelta
from typing import Any

import pytest
from django.core.exceptions import ValidationError
from django.db import transaction
from pytest_django import Settings

from apps.control.models import AuditAction, AuditEvent, EditEvent
from apps.core.tenancy import ShopMismatch, shop_context
from apps.shops.models import Closure, ClosureStatus, Shop
from apps.shops.selectors import closed_days, shop_today
from apps.shops.services import add_closure, cancel_closure, change_last_day
from tests.concurrency import in_another_transaction, wait_until_someone_waits_for_me

pytestmark = pytest.mark.django_db


def day(shop: Shop, offset: int) -> date:
    # A day counted from the shop's today: day(shop, -1) is yesterday.
    return shop_today(shop) + timedelta(days=offset)


def closure(shop: Shop, first: int, last: int, *, name: str = "Msiba wa bibi") -> Closure:
    # A closure saved straight to the table, so a test can start from one that began in the past, which add_closure
    # would refuse (test_add_closure.py).
    with shop_context(shop):
        row = Closure(shop=shop, first_day=day(shop, first), last_day=day(shop, last), name=name)
        row.full_clean()
        row.save()
        return row


def refusal_codes(refused: ValidationError) -> dict[str, list[str | None]]:
    # Each field's codes, as the API's error handler reads them (apps/core/api/errors.py). A refusal of the whole
    # action, such as a closure already cancelled, names no field: filed here under "__all__", where full_clean files a
    # rule of several fields, such as the overlap.
    if hasattr(refused, "error_dict"):
        return {field: [error.code for error in errors] for field, errors in refused.error_dict.items()}
    return {"__all__": [error.code for error in refused.error_list]}


def refused_with(work: Any) -> dict[str, list[str | None]]:
    with pytest.raises(ValidationError) as refused:
        work()
    return refusal_codes(refused.value)


def audit_lines(shop: Shop, row: Closure) -> list[tuple[str, str, Any, Any, Any]]:
    with shop_context(shop):
        return list(
            AuditEvent.objects.filter(subject_type="closure", subject_id=row.pk)
            .order_by("created_at", "id")
            .values_list("action", "reason", "created_by_id", "before", "after")
        )


def history(shop: Shop, row: Closure) -> list[tuple[Any, Any, Any]]:
    with shop_context(shop):
        return list(
            EditEvent.objects.filter(subject_type="closure", subject_id=row.pk)
            .order_by("created_at", "id")
            .values_list("created_by_id", "before", "after")
        )


def status_of(shop: Shop, row: Closure) -> str:
    with shop_context(shop):
        return Closure.objects.get(pk=row.pk).status


# Ondoa: a closure cancelled up to its first day.


def test_cancel_writes_an_audit_line(shop_a: Shop, staff_a: Any) -> None:
    # Planned for next week, then called off: cancelled, its days open again, and both books name who did it, the audit
    # trail with why.
    row = closure(shop_a, 3, 5)
    with shop_context(shop_a):
        cancel_closure(row, reason="Familia imeahirisha", by=staff_a)
        assert closed_days(shop_a, day(shop_a, 0), day(shop_a, 10)) == set()
    assert status_of(shop_a, row) == ClosureStatus.CANCELLED
    assert audit_lines(shop_a, row) == [
        (AuditAction.CLOSURE_CANCEL, "Familia imeahirisha", staff_a.pk, {"status": "active"}, {"status": "cancelled"})
    ]
    assert history(shop_a, row) == [(staff_a.pk, {"status": "active"}, {"status": "cancelled"})]


def test_cancel_on_its_first_day_allowed(shop_a: Shop) -> None:
    # It starts today, and today is still open: the shop opens after all.
    row = closure(shop_a, 0, 2)
    with shop_context(shop_a):
        cancel_closure(row, reason="Tunafungua", by=None)
    assert status_of(shop_a, row) == ClosureStatus.CANCELLED


def test_cancel_needs_a_reason(shop_a: Shop) -> None:
    # Spaces alone are no reason (rule 7), beside the reason's box; nothing changes.
    row = closure(shop_a, 3, 5)
    with shop_context(shop_a):
        assert refused_with(lambda: cancel_closure(row, reason="   ", by=None)) == {
            "reason": ["closure.reason_required"]
        }
    assert status_of(shop_a, row) == ClosureStatus.ACTIVE


def test_cancel_of_a_started_closure_refused(shop_a: Shop) -> None:
    # Yesterday was already closed, and may be worked out: cancelling would open it again. The owner moves the last day
    # instead.
    row = closure(shop_a, -1, 2)
    with shop_context(shop_a):
        assert refused_with(lambda: cancel_closure(row, reason="Tunafungua", by=None)) == {
            "__all__": ["closure.started"]
        }
    assert status_of(shop_a, row) == ClosureStatus.ACTIVE


def test_cancel_of_a_cancelled_closure_refused(shop_a: Shop) -> None:
    row = closure(shop_a, 3, 5)
    with shop_context(shop_a):
        cancel_closure(row, reason="Imeahirishwa", by=None)
        assert refused_with(lambda: cancel_closure(row, reason="Tena", by=None)) == {"__all__": ["closure.not_active"]}
    assert len(audit_lines(shop_a, row)) == 1


@pytest.mark.django_db(transaction=True)
def test_two_cancels_at_once_take_turns(shop_a: Shop) -> None:
    # Two managers press Ondoa at the same moment. The second waits for the closure's row, which the first holds until
    # it commits, then reads it cancelled and is refused: one cancel, one audit line. transaction=True, as in
    # test_day_in_order.py, so the second manager's connection sees the rows at all.
    row = closure(shop_a, 3, 5)

    def second_manager_cancels() -> object:
        with shop_context(shop_a.pk):
            return cancel_closure(row, reason="Pia mimi", by=None)

    with shop_context(shop_a), transaction.atomic():
        cancel_closure(row, reason="Imeahirishwa", by=None)
        second, ended = in_another_transaction(second_manager_cancels)
        wait_until_someone_waits_for_me()
    second.join(timeout=5)
    assert not second.is_alive(), "The second cancel still waits after the first committed."
    (refused,) = ended
    assert isinstance(refused, ValidationError)
    assert refusal_codes(refused) == {"__all__": ["closure.not_active"]}
    assert [reason for _action, reason, *_rest in audit_lines(shop_a, row)] == ["Imeahirishwa"]


# The last day moved, earlier or later.


def test_last_day_moved_earlier_reopens_from_today_on(shop_a: Shop, staff_a: Any) -> None:
    # The funeral closed the shop from two days ago to two days on; the family finished yesterday, so the owner sets the
    # last day to yesterday: the shop is open from today. Both books keep the old and the new last day, naming who.
    row = closure(shop_a, -2, 2)
    with shop_context(shop_a):
        change_last_day(row, last_day=day(shop_a, -1), reason="Familia imemaliza", by=staff_a)
        assert closed_days(shop_a, day(shop_a, -5), day(shop_a, 5)) == {day(shop_a, -2), day(shop_a, -1)}
    was, now = str(day(shop_a, 2)), str(day(shop_a, -1))
    assert audit_lines(shop_a, row) == [
        (AuditAction.CLOSURE_LAST_DAY, "Familia imemaliza", staff_a.pk, {"last_day": was}, {"last_day": now})
    ]
    assert history(shop_a, row) == [(staff_a.pk, {"last_day": was}, {"last_day": now})]


def test_last_day_never_reopens_a_past_day(shop_a: Shop) -> None:
    # Moved to two days ago, yesterday would open again after it was closed and perhaps worked out: refused, beside the
    # last day's box.
    row = closure(shop_a, -3, 2)
    with shop_context(shop_a):
        refusal = refused_with(lambda: change_last_day(row, last_day=day(shop_a, -2), reason="Kosa", by=None))
    assert refusal == {"last_day": ["closure.date_past"]}


def test_ended_closure_never_grows_over_past_days(shop_a: Shop, shop_b: Shop) -> None:
    # A closure that ended three days ago can't grow: the two days after it are past, and were open. One that ended
    # yesterday grows from today on. In two shops, so the two closures share no day.
    long_ago = closure(shop_a, -5, -3)
    yesterday = closure(shop_b, -2, -1, name="Hesabu ya mwaka")
    with shop_context(shop_a):
        refusal = refused_with(lambda: change_last_day(long_ago, last_day=day(shop_a, 1), reason="Kosa", by=None))
        assert refusal == {"last_day": ["closure.date_past"]}
    with shop_context(shop_b):
        change_last_day(yesterday, last_day=day(shop_b, 1), reason="Tunaendelea kuhesabu", by=None)
        assert closed_days(shop_b, day(shop_b, -5), day(shop_b, 5)) == {day(shop_b, n) for n in (-2, -1, 0, 1)}


def test_last_day_moved_later_never_overlaps(shop_a: Shop) -> None:
    # Days 1–2, and Krismasi on days 4–5: the first can't grow into day 4.
    row = closure(shop_a, 1, 2)
    closure(shop_a, 4, 5, name="Krismasi")
    with shop_context(shop_a):
        refusal = refused_with(lambda: change_last_day(row, last_day=day(shop_a, 4), reason="Zaidi", by=None))
        assert refusal == {"__all__": ["closure.overlaps"]}
        change_last_day(row, last_day=day(shop_a, 3), reason="Zaidi", by=None)


def test_last_day_before_first_refused(shop_a: Shop) -> None:
    row = closure(shop_a, 2, 4)
    with shop_context(shop_a):
        refusal = refused_with(lambda: change_last_day(row, last_day=day(shop_a, 1), reason="Kosa", by=None))
    assert refusal == {"last_day": ["closure.ends_before_it_starts"]}


def test_last_day_needs_a_reason(shop_a: Shop) -> None:
    row = closure(shop_a, 2, 4)
    with shop_context(shop_a):
        refusal = refused_with(lambda: change_last_day(row, last_day=day(shop_a, 3), reason="", by=None))
    assert refusal == {"reason": ["closure.reason_required"]}


def test_last_day_of_a_cancelled_closure_refused(shop_a: Shop) -> None:
    row = closure(shop_a, 2, 4)
    with shop_context(shop_a):
        cancel_closure(row, reason="Imeahirishwa", by=None)
        refusal = refused_with(lambda: change_last_day(row, last_day=day(shop_a, 6), reason="Zaidi", by=None))
    assert refusal == {"__all__": ["closure.not_active"]}


def test_same_last_day_changes_nothing(shop_a: Shop) -> None:
    # Saved with the day it already has: nothing to write in either book.
    row = closure(shop_a, 2, 4)
    with shop_context(shop_a):
        change_last_day(row, last_day=day(shop_a, 4), reason="Hakuna kipya", by=None)
    assert audit_lines(shop_a, row) == []
    assert history(shop_a, row) == []


@pytest.mark.django_db(transaction=True)
def test_a_move_and_an_add_at_once_take_turns(shop_a: Shop) -> None:
    # One manager moves a closure's last day from day 2 to day 4 while another adds a closure of days 4–5. Each alone is
    # fine; together they share day 4. The move holds the shop's row until it commits, so the add waits, then sees the
    # moved last day and is refused with its code. Without the move's lock on the shop, the add would check the old last
    # day, pass, and meet the database's own rule at the insert: an error no screen can explain. transaction=True, as in
    # test_two_cancels_at_once_take_turns.
    row = closure(shop_a, 1, 2)

    def second_manager_adds() -> object:
        with shop_context(shop_a.pk):
            return add_closure(shop_a, first_day=day(shop_a, 4), last_day=day(shop_a, 5), name="Mapumziko", by=None)

    with shop_context(shop_a), transaction.atomic():
        change_last_day(row, last_day=day(shop_a, 4), reason="Msiba umeongezeka", by=None)
        second, ended = in_another_transaction(second_manager_adds)
        wait_until_someone_waits_for_me()
    second.join(timeout=5)
    assert not second.is_alive(), "The add still waits after the move committed."
    (refused,) = ended
    assert isinstance(refused, ValidationError)
    assert refusal_codes(refused) == {"__all__": ["closure.overlaps"]}
    with shop_context(shop_a):
        assert list(Closure.objects.values_list("name", "last_day")) == [("Msiba wa bibi", day(shop_a, 4))]


# The demo, and the shop.


def test_demo_closures_change_from_tomorrow(shop_a: Shop, staff_a: Any, settings: Settings) -> None:
    # On the demo a visitor's change must leave today as the seed made it, for every visitor after them: moving a last
    # day so that today opens, or cancelling a closure that starts today, is refused. A change from tomorrow on is not,
    # and the system, as the seed acts, may change today too.
    settings.DEMO_SEED = True
    running = closure(shop_a, -2, 2)
    with shop_context(shop_a):
        # Ending it yesterday would open today.
        refusal = refused_with(lambda: change_last_day(running, last_day=day(shop_a, -1), reason="Mfano", by=staff_a))
        assert refusal == {"last_day": ["demo.closures_from_tomorrow"]}
        # Ending it today opens only tomorrow and the day after.
        change_last_day(running, last_day=day(shop_a, 0), reason="Mfano", by=staff_a)
        # The system may open today.
        change_last_day(running, last_day=day(shop_a, -1), reason="Mfumo", by=None)
        starts_today = closure(shop_a, 0, 2, name="Siku ya mfano")
        assert refused_with(lambda: cancel_closure(starts_today, reason="Mfano", by=staff_a)) == {
            "__all__": ["demo.closures_from_tomorrow"]
        }
        cancel_closure(starts_today, reason="Mfumo", by=None)
    assert status_of(shop_a, starts_today) == ClosureStatus.CANCELLED


def test_change_checks_the_shop(shop_a: Shop, staff_b: Any) -> None:
    # A bug in the calling code, not a person's mistake: shop B's manager can't change shop A's closure.
    row = closure(shop_a, 3, 5)
    with shop_context(shop_a):
        with pytest.raises(ShopMismatch):
            cancel_closure(row, reason="Hapana", by=staff_b)
        with pytest.raises(ShopMismatch):
            change_last_day(row, last_day=day(shop_a, 6), reason="Hapana", by=staff_b)
    assert status_of(shop_a, row) == ClosureStatus.ACTIVE
