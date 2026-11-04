"""apps/people/api/pin_session.py — the badge a PIN login gives: a Django session for one person on one device (AUTH-4;
03 §5.9).

A session is one row the server keeps, and a number the browser holds in a cookie. So a badge can be torn up at once,
and whatever it says about who stands here can't be changed by the browser. It is the same kind of session a password
starts (ADR-0038), so allauth and DRF both recognise it; a mark inside it, PIN_SESSION, is what makes it a PIN's.

This file owns that mark, and the one function that starts a badge.
"""

from django.contrib.auth import login
from rest_framework.request import Request

from apps.people.models import Device, StaffMember

# Where a badge keeps what it names, in the session's own row.
PIN_SESSION = "pin_session"


def start_pin_session(request: Request, staff: StaffMember, device: Device, *, idle_minutes: int) -> None:
    """Give this browser a new badge for this person on this device, which ends after `idle_minutes` with no use."""
    visit = request._request
    # One badge per device: whatever this browser holds is torn up first, on the server too, whoever's it was.
    visit.session.flush()
    login(visit, staff.user)
    # What each visit will check (03 §5.9). It names the job, not only the person: someone with jobs at two shops is at
    # this device's shop here. Kept on the server: the browser holds only the badge's number.
    visit.session[PIN_SESSION] = {"shop": str(staff.shop_id), "staff": str(staff.pk), "device": str(device.pk)}
    visit.session.set_expiry(idle_minutes * 60)
