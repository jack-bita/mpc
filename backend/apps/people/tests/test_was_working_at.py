"""apps/people/tests/test_was_working_at.py — whether a person was working at a given moment, for a record a laptop
made offline (was_working_at, apps/people/selectors.py; SYNC-5, X2).

    Juma's status history                     a moment         working?
    suspended 11:00                           12:00            no
    suspended 11:00, brought back 14:00       12:00            no      (he is back now, but wasn't then)
    left (recorded now)                       a minute later   no

The push asks it of a record's maker (apps/sync/push.py); its flags are tested there (test_maker_checks.py). These are
the edges of the question itself. Fake data only: the repo is public (03 §10).
"""

import datetime as dt

import pytest

from apps.control.models import AuditEvent
from apps.core.tenancy import shop_context
from apps.people.models import StaffMember
from apps.people.selectors import shop_today, was_working_at
from apps.people.services import mark_left
from apps.shops.models import Shop

pytestmark = pytest.mark.django_db


def _moves(staff: StaffMember) -> list[dt.datetime]:
    # When each of the person's status moves happened, oldest first, as the audit trail stamped them.
    with shop_context(staff.shop_id):
        return list(
            AuditEvent.objects.filter(subject_type="staff", subject_id=staff.pk)
            .order_by("created_at")
            .values_list("created_at", flat=True)
        )


def test_a_leaving_recorded_after_the_person_was_read_still_counts(shop_a: Shop, staff_a: StaffMember) -> None:
    # The push reads a record's maker before the record's own transaction; the owner records that Juma left just then.
    # The copy in hand still says "active", but the question reads his status as it is now (SYNC-5's review).
    with shop_context(shop_a):
        copy_read_before = StaffMember.objects.get(pk=staff_a.pk)
        mark_left(staff_a, left_on=shop_today(shop_a), by=None, reason="Amehamia Moshi")
        [left_at] = _moves(staff_a)
        assert not was_working_at(copy_read_before, left_at + dt.timedelta(minutes=1))
