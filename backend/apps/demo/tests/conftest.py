"""apps/demo/tests/conftest.py — the demo's tests make the shop without its three weeks of taps, unless a test asks for
them (DATA-8).

The taps go through the push one by one, as a laptop's do, which costs the seed some 3 seconds; the demo's tests make
the shop some 65 times, so every run of them would wait over 3 minutes more, for taps most of them never read. So the
seed runs here with no days before today (HISTORY_DAYS 0): its rules, its people and their rates start today, as before
DATA-8, and the laptop is paired but sends nothing. A test about the taps, the days they make or the change log they
fill takes `three_weeks`, and gets the seed as the demo runs it. The browser tests (make check-e2e) always run it whole.
"""

import pytest

from apps.demo import services

# The demo's own span, read once as the module is loaded, before any test makes it 0.
THREE_WEEKS = services.HISTORY_DAYS


@pytest.fixture(autouse=True)
def no_days_before_today(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(services, "HISTORY_DAYS", 0)


@pytest.fixture
def three_weeks(monkeypatch: pytest.MonkeyPatch, no_days_before_today: None) -> None:
    # After the autouse fixture, which it names so it runs first: the demo's own span again.
    monkeypatch.setattr(services, "HISTORY_DAYS", THREE_WEEKS)
