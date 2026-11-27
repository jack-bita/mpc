"""apps/staffpay/services/mine.py — a worker's own days and pay, as they read them themselves (WAGE-4, 02 A4): Siku na
malipo yangu.

Asha types her PIN on the Dawa laptop and opens her own month: the calendar Baba sees of her, and her pay, line by line,
as Mishahara shows it. A4: she sees only her own, so the route hands this file the one job her login names, never one
she asks for (`apps/staffpay/api/views.py`, MineViewSet).

Nothing here works anything out again. Each read is the manager's own (worker_attendance, worker_pay), so Asha's page
and Baba's can never say two different things about her November. What this file adds is what only a worker's own
look needs: the months she may ask for, and the one value of a tap she reads differently. What she is shown of the
answer, and what is left out (a tap's photo and its doubt, the day's choices, the payslip's id, the signature), is the
serializers' list (`OwnAttendanceAnswer`, `OwnPayAnswer`), so a field a later card adds to the manager's answer never
reaches her by itself.
"""

import datetime as dt
from dataclasses import replace

from django.core.exceptions import PermissionDenied, ValidationError

from apps.core.tenancy import ShopMismatch
from apps.people.models import StaffMember, StaffStatus
from apps.shops.models import Shop
from apps.shops.selectors import shop_today
from apps.staffpay.services.attendance import TapLine, WorkerAttendance, worker_attendance
from apps.staffpay.services.book import month_span
from apps.staffpay.services.pay import WorkerPayMonth, worker_pay


def own_attendance(shop: Shop, job: StaffMember, month: dt.date) -> WorkerAttendance:
    """The month of `month`, any day of it, of `job`, as its own worker reads it (WAGE-4): the manager's very answer
    (worker_attendance), worked out through the book as his is, so it writes as the book does, and asked twice writes
    nothing the second time. Asked as the worker, so no day of it offers a choice: nobody decides their own day (ATT-6).
    A job not working now, or a month before the job's first, or one still to come, is refused. The shop must be open,
    and the job one of it."""
    first = _check_own_month(shop, job, month)
    answer = worker_attendance(shop, job, first, viewer=job)
    return replace(answer, taps=[_as_own(tap) for tap in answer.taps])


def own_pay(shop: Shop, job: StaffMember, month: dt.date) -> WorkerPayMonth:
    """The pay of `job` of the month of `month`, any day of it, as its own worker reads it (WAGE-4): the very line
    Mishahara shows of them (worker_pay), so the two pages never say two totals. A job not working now, or a month
    before the job's first, or one still to come, is refused. The shop must be open, and the job one of it."""
    return worker_pay(shop, job, _check_own_month(shop, job, month))


def _check_own_month(shop: Shop, job: StaffMember, month: dt.date) -> dt.date:
    # The job is the shop's (T1), asked first: the route finds it through the guard, so another shop's never comes
    # here, but given one by a bug, this fails loudly, before the status below is read through a guard that hides it.
    if job.shop_id != shop.pk:
        raise ShopMismatch("A worker's own reads were given a job of another shop.")
    # Only one working here now reads their own (X2): a suspended person, and one who left, read nothing, whoever asks.
    # Its status read afresh, through the guard, never the copy the caller holds, which a login may have loaded before
    # the job stopped. A real login already refuses both (`staff.suspended`, no job for one who left); this is the
    # rule's own place, so no other caller can skip it (the review). A refusal of a person, as a missing key is.
    if StaffMember.objects.values_list("status", flat=True).get(pk=job.pk) != StaffStatus.ACTIVE:
        # English for the logs; the screens translate the code (ADR-0032).
        raise PermissionDenied("This person is not working here now.")
    # The months a worker's own page offers, from the month of their job's first day up to the shop's own month, and the
    # first day of the one asked. Anything else is a slip of a typed address, said as one, never an empty month, which
    # would read as "you never came" (Asha in August, hired in September). A job's own first day, never the person's:
    # one hired again (PPL-11) reads the job they are logged in as, and its months begin with it (04 §20, 32).
    # A whole request's refusal, with no field: the page shows its sentence as it is (ApiErrorAlert).
    first, _ = month_span(month)
    if first > shop_today(shop):
        raise ValidationError("A month still to come has no days yet.", code="mine.month_to_come")
    if first < job.started_on.replace(day=1):
        raise ValidationError("This job had not started in this month.", code="mine.before_job")
    return first


def _as_own(tap: TapLine) -> TapLine:
    # A tap's time as its worker reads it: the one the server trusts, or, for a tap it trusts none of, the laptop's own
    # clock, said as not trusted (ATT-1), as it is then the only time there is. Beside a trusted time, the laptop's own
    # says only whether that laptop's clock was off: the shop's check on its laptops, not the worker's to read, as a
    # tap's doubt isn't (WAGE-4).
    return tap if tap.time is None else replace(tap, laptop_time=None)
