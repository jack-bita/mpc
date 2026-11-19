"""apps/staffpay/services.py — the writes of attendance and pay: the book of days (ATT-10; 02 §12).

    work_out_days(MPC, 16 Nov, 22 Nov)  → each job's day of that week, worked out, kept and answered:
    Asha   Mon 16 Nov  late          500.00  07:50  18:45
    Juma   Mon 16 Nov  needs_review  0.00    07:20  —          no Toka: a manager decides (ATT-6)

The day's rule (work_out_day, apps/staffpay/calculations.py) says what one day was; the book finds each day's taps and
rules, hands them in, and keeps the answer, one row per job and date (AttendanceDay). Nothing here is typed by a person:
the days are answers, worked out again each time they are asked for, as a tap can come late from a laptop that was
offline, and the owner can change a rule for days already past. ATT-5 asks for a month to show, WAGE-2 for a month to
pay, ATT-7 each night. No route of its own, and no line in the change log: no laptop keeps a copy of the days.
"""

import datetime as dt
import uuid
from collections import defaultdict
from zoneinfo import ZoneInfo

from django.db import transaction
from django.db.models import Q

from apps.core.tenancy import ALL_SHOPS, ShopMismatch, current_shop
from apps.people.models import StaffMember
from apps.shops.models import Shop
from apps.staffpay.calculations import Tap, shop_minute, work_out_day
from apps.staffpay.models import AttendanceDay, AttendanceEvent, ClockKind
from apps.staffpay.selectors import day_rules, rules_as_text

# What the book works out on a day, and so what it writes again when a day comes out otherwise. Not the job, the date
# or the shop, which say which day it is; nor `created_at`, which says when the day was first kept.
WORKED_OUT = ["status", "fine", "first_in", "first_out", "rules_used"]


def work_out_days(shop: Shop, first: dt.date, last: dt.date) -> list[AttendanceDay]:
    """Work out and keep each job's day from `first` to `last`, both counted, and answer them, date by date. A day that
    comes out as it was kept is not written again. The shop must be open: the visit's own, or a system job's."""
    # A shop must be open, and be this one, as for get_setting and closed_days: through the guard, another shop's taps
    # would be hidden, and its workers' days kept as absent without a word. So fail closed (ADR-0022).
    opened = current_shop()
    if opened is not ALL_SHOPS and opened != shop.pk:
        raise ShopMismatch("work_out_days was given a shop that is not the one open.")
    # A datetime is a kind of date in Python, but a moment, not the shop's day: in UTC, 22:00 on 15 Nov is already
    # 16 Nov in Arusha. The rules and the closed days take the shop's dates, so the book does too.
    if isinstance(first, dt.datetime) or isinstance(last, dt.datetime):
        raise TypeError("work_out_days needs the shop's business dates, not datetimes.")
    zone = ZoneInfo(shop.timezone)
    dates = [first + dt.timedelta(days=n) for n in range((last - first).days + 1)]
    # One transaction, so what the book answers is what it kept: the taps, the days kept and the writes read one
    # moment of the database's.
    with transaction.atomic():
        # Every job, in the order of their ids, so two runs at once write their rows in the same order and never wait
        # for each other's: one per job, as a person who left and is hired again the same day has two (PPL-11).
        jobs = list(StaffMember.objects.filter(shop=shop).order_by("pk"))
        taps = _taps(shop, first, last, zone)
        kept = {
            (row.staff_id, row.date): row for row in AttendanceDay.objects.filter(shop=shop, date__range=(first, last))
        }
        answered: list[AttendanceDay] = []
        for day in dates:
            # The day's rules, once per date for every job: nine reads, never nine per worker (A1).
            rules = day_rules(shop, day)
            rules_used = rules_as_text(rules)
            for job in jobs:
                # Only the job's own taps: Asha's on Asha's day, even on a laptop Juma used too. With none, the rule
                # answers absent.
                result = work_out_day(taps.get((job.pk, day), []), rules)
                answered.append(
                    AttendanceDay(
                        shop=shop,
                        staff=job,
                        date=day,
                        status=result.status,
                        fine=result.fine,
                        first_in=result.first_in,
                        first_out=result.first_out,
                        # A copy for each day (T4): one day's rules are never another's object, so nothing done to one
                        # could reach the other.
                        rules_used=dict(rules_used),
                    )
                )
        return _keep(answered, kept)


def _taps(shop: Shop, first: dt.date, last: dt.date, zone: ZoneInfo) -> dict[tuple[uuid.UUID, dt.date], list[Tap]]:
    # Each job's taps on each date from `first` to `last`, as the rule reads them. A day's edges are the shop's own
    # midnights, not UTC's: Asha's tap at 21:30 UTC on Monday is Tuesday's, at 00:30 in Arusha. So the span is read from
    # the midnight starting its first day to the one ending its last, each a moment with its zone.
    start = dt.datetime.combine(first, dt.time.min, tzinfo=zone)
    end = dt.datetime.combine(last + dt.timedelta(days=1), dt.time.min, tzinfo=zone)
    lines = (
        # A voided tap counts for nothing (T2): a clock-in tapped twice by mistake, voided by a manager (ATT-6).
        AttendanceEvent.objects.filter(shop=shop, voided_at__isnull=True)
        .filter(
            # By the time the server trusts, never the laptop's, whose clock anyone can move (ATT-1): through the
            # index on (shop, trusted_time). One with no trusted time (`unverified`) by the laptop's time instead,
            # the only one it has: its day needs review anyway, but it must land on a day for a manager to see it.
            Q(trusted_time__gte=start, trusted_time__lt=end)
            | Q(trusted_time__isnull=True, client_time__gte=start, client_time__lt=end)
        )
        .values_list("staff_id", "kind", "trusted_time", "client_time")
    )
    taps: dict[tuple[uuid.UUID, dt.date], list[Tap]] = defaultdict(list)
    for staff_id, kind, trusted_time, client_time in lines:
        # Its date on the shop's calendar, by its trusted time, or by the laptop's for one with none.
        day = (trusted_time if trusted_time is not None else client_time).astimezone(zone).date()
        # Its minute on the shop's clock, its seconds dropped, as the counter showed it (shop_minute): 07:35:40 is
        # 07:35, on time. None for a tap with no trusted time, which sends the day to review (ATT-4).
        minute = shop_minute(trusted_time, zone) if trusted_time is not None else None
        taps[(staff_id, day)].append(Tap(ClockKind(kind), minute))
    return taps


def _keep(answered: list[AttendanceDay], kept: dict[tuple[uuid.UUID, dt.date], AttendanceDay]) -> list[AttendanceDay]:
    # Keep each day the book worked out, and answer the rows as kept. A day that came out as it was kept is answered as
    # it was, and not written again: the edit history keeps only real changes (a tap that came late, a rule changed for
    # days past), and a month asked for twice writes nothing the second time.
    rows: list[AttendanceDay] = []
    changed: list[AttendanceDay] = []
    new: list[AttendanceDay] = []
    for day in answered:
        old = kept.get((day.staff_id, day.date))
        if old is None:
            new.append(day)
            rows.append(day)
            continue
        if any(getattr(old, part) != getattr(day, part) for part in WORKED_OUT):
            # Changed: the kept row takes the new answer, so it keeps its id and the day it was first kept.
            for part in WORKED_OUT:
                setattr(old, part, getattr(day, part))
            changed.append(old)
        rows.append(old)
    # A day kept before: an UPDATE by its id, which the edit history's trigger writes down (ADR-0036), Asha's Monday
    # from on time to late. In the order the days were worked out, as every run writes them.
    if changed:
        AttendanceDay.objects.bulk_update(changed, WORKED_OUT)
    # A day kept for the first time: an INSERT, or, when another run kept the same day a moment before (two managers
    # open the month at once), an UPDATE of that row instead, by the rule of one day per job and date. Both runs worked
    # out the same answer, so they end with the same row (an upsert).
    if new:
        AttendanceDay.objects.bulk_create(
            new, update_conflicts=True, unique_fields=["shop", "date", "staff"], update_fields=WORKED_OUT
        )
        # Then those rows are read back, as stored: after an UPDATE in place of the INSERT, the row kept is the other
        # run's, with its own id, while Django leaves on each day the id it made for it, which no row has. Read only
        # when a day was kept for the first time, the first time a month is asked for. A row of this span that is
        # none of these days (another job's, another date's) is left out by the lookup.
        stored = {
            (row.staff_id, row.date): row
            for row in AttendanceDay.objects.filter(
                shop_id=new[0].shop_id,
                date__in={day.date for day in new},
                staff_id__in={day.staff_id for day in new},
            )
        }
        rows = [stored.get((row.staff_id, row.date), row) for row in rows]
    return rows
