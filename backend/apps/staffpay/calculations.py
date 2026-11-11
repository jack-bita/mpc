"""apps/staffpay/calculations.py — pure sums for attendance and pay: no database, no clock of their own (03 §5.1).

The time check (ATT-1, 02 §12): how far a clock-in's time can be trusted, from the evidence about the laptop's clock.
A laptop's clock can be moved by anyone, and an offline clock-in carries only its time, so the server keeps that time
only when no sign says the clock moved. Server only: the laptop never judges its own clock, so this one has no
TypeScript twin and no shared test vectors (03 §8).
"""

import datetime as dt
from dataclasses import dataclass

from apps.staffpay.models import TimeCheck

# A clock-in the laptop sent within 2 minutes of the tap, both by its own clock, was made online: the push runs 2
# seconds after a new record (03 §6.5), and a retry or two still fits. Its time is the server's own.
ONLINE_WITHIN = dt.timedelta(minutes=2)
# How far two clocks may disagree before it is a sign the laptop's moved: a laptop's clock drifts a little while it
# is offline, and a push takes a moment to arrive. Past it, a worker could win a late fine's worth, so it stays small.
CLOCK_SLACK = dt.timedelta(minutes=2)


@dataclass(frozen=True)
class Evidence:
    # What the server knows of one clock-in's time (02 §12). Three times by the laptop's clock, which may be wrong.
    client_time: dt.datetime  # when the worker tapped
    sent_at: dt.datetime  # when the laptop sent the push
    time_before: dt.datetime | None  # its record numbered before this one; None for its first
    # And two the laptop's clock can't move.
    received_at: dt.datetime  # the server's clock as the push arrived
    last_server_time: dt.datetime  # the last time the server told the laptop, before the tap


@dataclass(frozen=True)
class CheckedTime:
    # The answer, copied onto the line (T4): how far its time can be trusted, the time trusted (None when it can't be),
    # and how far off the laptop's clock was as it sent (its clock minus the server's).
    time_check: TimeCheck
    trusted_time: dt.datetime | None
    clock_error: dt.timedelta


def check_time(evidence: Evidence) -> CheckedTime:
    """How far one clock-in's time can be trusted (02 §12): the server's time when it was sent at once; else the
    laptop's, when no sign says its clock moved; else none, for a manager to decide (ATT-6)."""
    # How far off the laptop's clock was as it sent: kept whatever the answer, so a manager can see it.
    clock_error = evidence.sent_at - evidence.received_at
    # How long it waited on the laptop, both ends by the laptop's own clock: a wrong clock is wrong at both ends, so
    # the wait is right. Below zero, the clock went back between the tap and the push, which is not "at once": sign
    # 4 below looks at it.
    waited = evidence.sent_at - evidence.client_time
    if dt.timedelta(0) <= waited <= ONLINE_WITHIN:
        return CheckedTime(TimeCheck.SERVER, evidence.received_at, clock_error)
    # Each sign compares the gap between two times with the slack, never a time moved by it: a time from year 1, which
    # a laptop's code can send, can't be moved 2 minutes earlier, and the crash would answer retry at every push.
    signs = (
        # 1. Its record before it has a later time: the clock went back between the two.
        evidence.time_before is not None and evidence.time_before - evidence.client_time > CLOCK_SLACK,
        # 2. Its time is before a time the server had already told the laptop.
        evidence.last_server_time - evidence.client_time > CLOCK_SLACK,
        # 3. The laptop's clock was off as it sent, slow or fast, so what it wrote that morning can't be believed.
        abs(clock_error) > CLOCK_SLACK,
        # 4. Its time is after the laptop's own clock as it sent: made "in the future", so the clock was moved forward
        # for the tap and set right again before the push, which no other sign sees (ATT-1's review).
        evidence.client_time - evidence.sent_at > CLOCK_SLACK,
    )
    if any(signs):
        return CheckedTime(TimeCheck.UNVERIFIED, None, clock_error)
    return CheckedTime(TimeCheck.DEVICE_OK, evidence.client_time, clock_error)
