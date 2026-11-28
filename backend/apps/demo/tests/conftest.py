"""apps/demo/tests/conftest.py — the demo's tests make the shop without its days before today, unless a test asks for
them (DATA-8, DATA-2).

The taps go through the push one by one, as a laptop's do, some 30 milliseconds each: the demo's days from the 1st of
last month hold some 300, which cost the seed some 15 seconds, and the demo's tests make the shop some 65 times, all
one after another, so every run would wait over a quarter of an hour more, for taps most of them never read. So the
seed runs here with no days before today (its first day is today): its rules, its people and their rates start today,
as before DATA-8, and the laptop is paired but sends nothing. A test about the newest days, the taps, their flags, the
meal money and the advances counted back from yesterday, or the change log they fill, takes `three_weeks`: DATA-8's
span, 21 days back, which holds every one of them. Only a test about the whole span, the month gone by, its pay and its
own days, or the shop as the demo makes it, takes `from_last_month`, and gets the seed as the demo runs it. The browser
tests (make check-e2e) always run it whole.
"""

from datetime import date, timedelta

import pytest

from apps.demo import services

# The demo's own first day, read once as the module is loaded, before any test replaces it.
HISTORY_STARTS = services._history_starts

# DATA-8's span, which holds every newest day: the odd days, the forgotten meal money and the advances counted back
# from yesterday reach 13 working days back, and 21 days hold 18.
THREE_WEEKS = timedelta(days=21)


@pytest.fixture(autouse=True)
def no_days_before_today(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(services, "_history_starts", lambda today: today)


@pytest.fixture
def three_weeks(monkeypatch: pytest.MonkeyPatch, no_days_before_today: None) -> None:
    # After the autouse fixture, which it names so it runs first.
    def three_weeks_back(today: date) -> date:
        return today - THREE_WEEKS

    monkeypatch.setattr(services, "_history_starts", three_weeks_back)


@pytest.fixture
def from_last_month(monkeypatch: pytest.MonkeyPatch, no_days_before_today: None) -> None:
    # After the autouse fixture, which it names so it runs first: the demo's own first day again.
    monkeypatch.setattr(services, "_history_starts", HISTORY_STARTS)
