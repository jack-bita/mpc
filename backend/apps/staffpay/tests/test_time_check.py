"""apps/staffpay/tests/test_time_check.py — the time check: how far a clock-in's time can be trusted, from the evidence
about the laptop's clock (check_time, apps/staffpay/calculations.py; ATT-1, 02 §12).

    sent within 2 minutes of the tap, by the laptop's own clock     → server: the server's time, whatever the clock said
    sent later, and no sign the clock moved                          → device_ok: the laptop's time
    sent later, and any one sign:                                    → unverified: no time trusted; a manager decides
      1. the laptop's record before it has a later time
      2. its time is before the last server time the laptop had seen
      3. as it sent the push, the laptop's clock was more than 2 minutes off the server's
      4. its time is after the laptop's own clock as it sent the push: the clock was moved forward for the tap

One morning at MPC, in Arusha's time: the Dawa laptop last heard from the server at 06:50; Asha taps Ingia at 07:20;
the power goes, and the laptop sends at 12:00, when it comes back. Pure: no database, no clock of its own. Fake data
only: the repo is public.
"""

import datetime as dt
from zoneinfo import ZoneInfo

from apps.staffpay.calculations import Evidence, Sign, check_time
from apps.staffpay.models import TimeCheck

ARUSHA = ZoneInfo("Africa/Dar_es_Salaam")


def arusha(hour: int, minute: int, second: int = 0) -> dt.datetime:
    # A time on 10 November 2026, as a clock in Arusha shows it.
    return dt.datetime(2026, 11, 10, hour, minute, second, tzinfo=ARUSHA)


def morning(**changes: object) -> Evidence:
    # The morning above, with nothing wrong: the laptop's clock right to the second. `changes` overrides a clue.
    clues: dict[str, object] = {
        "client_time": arusha(7, 20),
        "sent_at": arusha(12, 0),
        "received_at": arusha(12, 0),
        "last_server_time": arusha(6, 50),
        "time_before": arusha(7, 5),
    }
    clues.update(changes)
    return Evidence(**clues)  # type: ignore[arg-type]


def test_sent_at_once_takes_the_servers_time() -> None:
    # Asha taps at 07:20:00 and the laptop sends at 07:20:02, both by its clock: it was online, so the time is the
    # server's own, as the push arrived.
    checked = check_time(morning(sent_at=arusha(7, 20, 2), received_at=arusha(7, 20, 3)))
    assert (checked.time_check, checked.trusted_time) == (TimeCheck.SERVER, arusha(7, 20, 3))


def test_a_clock_moved_back_gains_nothing_online() -> None:
    # Juma arrives at 08:10, sets the laptop to 07:30 and taps; it sends two seconds later. The two seconds are right,
    # as both times come from the same wrong clock, so the time is the server's: 08:10, late.
    checked = check_time(
        morning(client_time=arusha(7, 30), sent_at=arusha(7, 30, 2), received_at=arusha(8, 10, 2), time_before=None)
    )
    assert (checked.time_check, checked.trusted_time) == (TimeCheck.SERVER, arusha(8, 10, 2))


def test_two_minutes_is_still_online_and_a_second_more_is_not() -> None:
    # The edge: a push the laptop retried after a short wait is still "at once"; one later than 2 minutes was offline.
    at_two = check_time(morning(sent_at=arusha(7, 22), received_at=arusha(7, 22)))
    after_two = check_time(morning(sent_at=arusha(7, 22, 1), received_at=arusha(7, 22, 1)))
    assert (at_two.time_check, after_two.time_check) == (TimeCheck.SERVER, TimeCheck.DEVICE_OK)


def test_sent_later_keeps_the_laptops_time_when_nothing_disagrees() -> None:
    # The morning as it was: sent at 12:00, its record before at 07:05, the server last seen at 06:50, the clock right.
    checked = check_time(morning())
    assert (checked.time_check, checked.trusted_time) == (TimeCheck.DEVICE_OK, arusha(7, 20))


def test_the_first_record_has_no_record_before_to_disagree() -> None:
    checked = check_time(morning(time_before=None))
    assert checked.time_check == TimeCheck.DEVICE_OK


def test_a_record_before_with_a_later_time_is_a_sign() -> None:
    # Sign 1: the sale before it says 08:05, yet Juma's clock-in after it says 07:30. The clock went back between them.
    checked = check_time(morning(client_time=arusha(7, 30), time_before=arusha(8, 5)))
    assert (checked.time_check, checked.trusted_time) == (TimeCheck.UNVERIFIED, None)


def test_a_time_before_the_last_server_time_seen_is_a_sign() -> None:
    # Sign 2: the laptop had heard the server say 07:50, yet the clock-in after that says 07:30.
    checked = check_time(morning(client_time=arusha(7, 30), last_server_time=arusha(7, 50), time_before=None))
    assert (checked.time_check, checked.trusted_time) == (TimeCheck.UNVERIFIED, None)


def test_a_clock_off_at_sync_is_a_sign() -> None:
    # Sign 3: as it sent the push, the laptop's clock said 11:20 while the server's said 12:00: 40 minutes slow, so
    # the 07:20 it wrote that morning can't be believed either. A clock too fast is as wrong.
    slow = check_time(morning(sent_at=arusha(11, 20)))
    fast = check_time(morning(sent_at=arusha(12, 40)))
    assert (slow.time_check, slow.trusted_time) == (TimeCheck.UNVERIFIED, None)
    assert fast.time_check == TimeCheck.UNVERIFIED


def test_a_time_after_the_laptops_clock_at_sending_is_a_sign() -> None:
    # Sign 4: at 15:00 Juma takes the laptop off the network, sets it to 17:00, taps Toka, sets it right again and
    # plugs it back in; it sends at 15:01. A tap timed two hours after the laptop's own clock as it sent was made "in
    # the future": the clock was moved forward for it. Up to 2 minutes is no sign; a second past that is.
    juma = morning(
        client_time=arusha(17, 0), sent_at=arusha(15, 1), received_at=arusha(15, 1), last_server_time=arusha(14, 0)
    )
    assert (check_time(juma).time_check, check_time(juma).trusted_time) == (TimeCheck.UNVERIFIED, None)
    at_the_edge = morning(client_time=arusha(15, 3), sent_at=arusha(15, 1), received_at=arusha(15, 1))
    past_it = morning(client_time=arusha(15, 3, 1), sent_at=arusha(15, 1), received_at=arusha(15, 1))
    assert (check_time(at_the_edge).time_check, check_time(past_it).time_check) == (
        TimeCheck.DEVICE_OK,
        TimeCheck.UNVERIFIED,
    )


def test_the_check_names_each_sign_it_found() -> None:
    # Which signs, not only that there was one: sign 1 says two records disagree, so its flag names the maker of the
    # record before too (Jack, ATT-1's review). None, for a time kept or sent at once.
    assert check_time(morning()).signs == frozenset()
    assert check_time(morning(sent_at=arusha(7, 20, 2), received_at=arusha(7, 20, 2))).signs == frozenset()
    assert check_time(morning(client_time=arusha(7, 30), time_before=arusha(8, 5))).signs == {
        Sign.RECORD_BEFORE_IS_LATER
    }
    everything_wrong = morning(
        client_time=arusha(7, 30), time_before=arusha(8, 5), last_server_time=arusha(7, 50), sent_at=arusha(6, 0)
    )
    assert check_time(everything_wrong).signs == {
        Sign.RECORD_BEFORE_IS_LATER,
        Sign.BEFORE_THE_LAST_SERVER_TIME,
        Sign.CLOCK_OFF_AT_SENDING,
        Sign.AFTER_SENDING,
    }


def test_two_minutes_off_is_not_yet_a_sign() -> None:
    # A laptop's clock drifts a little while it is offline, and a push takes a moment to arrive: up to 2 minutes, either
    # way, in each comparison, is no sign. A second past that is.
    within = morning(
        client_time=arusha(7, 20), time_before=arusha(7, 22), last_server_time=arusha(7, 22), sent_at=arusha(11, 58)
    )
    assert check_time(within).time_check == TimeCheck.DEVICE_OK
    for beyond in (
        morning(client_time=arusha(7, 20), time_before=arusha(7, 22, 1)),
        morning(client_time=arusha(7, 20), last_server_time=arusha(7, 22, 1)),
        morning(sent_at=arusha(11, 57, 59)),
    ):
        assert check_time(beyond).time_check == TimeCheck.UNVERIFIED


def test_times_at_the_ends_of_the_calendar_still_get_an_answer() -> None:
    # A laptop's code can send a time from year 1, and the answer log can hold one. The check compares gaps between
    # two times, never a time moved by 2 minutes, which year 1 can't be: a crash here would answer retry at every
    # push, and that laptop's whole outbox would wait behind this clock-in forever (ATT-1's review).
    year_one = dt.datetime(1, 1, 1, tzinfo=dt.UTC)
    last_day = dt.datetime(9999, 12, 31, 23, 59, tzinfo=dt.UTC)
    assert check_time(morning(last_server_time=year_one, time_before=year_one)).time_check == TimeCheck.DEVICE_OK
    assert check_time(morning(last_server_time=last_day)).time_check == TimeCheck.UNVERIFIED
    assert check_time(morning(time_before=last_day)).time_check == TimeCheck.UNVERIFIED


def test_the_clock_error_is_the_laptops_clock_minus_the_servers() -> None:
    # Kept on the line as evidence, whatever the answer: 40 minutes slow is minus 40 minutes; right is zero.
    assert check_time(morning(sent_at=arusha(11, 20))).clock_error == dt.timedelta(minutes=-40)
    assert check_time(morning()).clock_error == dt.timedelta(0)
