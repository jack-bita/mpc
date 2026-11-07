"""apps/people/api/pin_session.py — the badge a PIN login gives: a Django session for one person on one device (AUTH-4;
03 §5.9).

A session is one row the server keeps, and a number the browser holds in a cookie. So a badge can be torn up at once,
and whatever it says about who stands here can't be changed by the browser. It is the same kind of session a password
starts (ADR-0038), so allauth and DRF both recognise it; a mark inside it, PIN_SESSION, is what makes it a PIN's.

What each visit checks of a badge lives with the other rules of who may act (job_of_pin_session,
apps/people/selectors.py). This file owns the badge's mark, the one function that starts a badge, the one that keeps
it alive, and the one that says how long it lasts unused, for the screen's own idle timer (UI-4).
"""

import time

from django.contrib.auth import login
from django.contrib.sessions.backends.base import SessionBase
from rest_framework.request import Request

from apps.people.models import Device, StaffMember
from apps.people.selectors import pin_stamp

# Where a badge keeps what it names, in the session's own row.
PIN_SESSION = "pin_session"
# When it was last used, in seconds since 1970.
PIN_SESSION_USED = "pin_session_used"
# How often use pushes the idle time forward.
KEEP_ALIVE_EVERY_SECONDS = 60


def start_pin_session(request: Request, staff: StaffMember, device: Device, *, idle_minutes: int) -> None:
    """Give this browser a new badge for this person on this device, which ends after `idle_minutes` with no use."""
    visit = request._request
    # One badge per device: whatever this browser holds is torn up first, on the server too, whoever's it was.
    visit.session.flush()
    login(visit, staff.user)
    # What each visit will check (03 §5.9). It names the job, not only the person: someone with jobs at two shops is at
    # this device's shop here. Kept on the server: the browser holds only the badge's number.
    visit.session[PIN_SESSION] = {
        "shop": str(staff.shop_id),
        "staff": str(staff.pk),
        "device": str(device.pk),
        "pin_set_at": pin_stamp(staff),
    }
    visit.session[PIN_SESSION_USED] = int(time.time())
    visit.session.set_expiry(idle_minutes * 60)


def keep_pin_session_alive(session: SessionBase) -> None:
    """Called at each visit that passes: use pushes the idle time forward. At most once a minute, as a busy screen sends
    many requests, and each save is a write; at a short idle time, at half of it. So a badge can end up to a minute
    early, or half a short idle time, which nobody will notice."""
    now = int(time.time())
    # Sooner for a short idle time: a shop may set 1 minute (IDLE_MINUTES), and waiting a whole minute to push it would
    # always come too late, so a person in the middle of their work would be logged out. Half the idle time leaves room,
    # and a badge then ends at most half its idle time early.
    every = min(KEEP_ALIVE_EVERY_SECONDS, session.get_expiry_age() // 2)
    if now - session.get(PIN_SESSION_USED, 0) >= every:
        # Changing the session makes Django save it at the end of the visit, with a new end date, and send the cookie
        # again with a whole idle time.
        session[PIN_SESSION_USED] = now


def pin_session_idle_minutes(session: SessionBase) -> int | None:
    """How long this browser's badge lasts unused, in minutes; None if it holds no PIN's badge, as a password on a
    person's own phone doesn't. `me` sends it, so a shared laptop's screen locks when the badge ends (UI-4)."""
    if session.get(PIN_SESSION) is None:
        return None
    # The badge's own life, as start_pin_session set it and every save since has kept it: not the shop's setting today,
    # which the owner may have changed since. The server ends this badge by this number, so the screen must too.
    return session.get_expiry_age() // 60
