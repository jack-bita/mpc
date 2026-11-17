"""apps/core/tests/test_zoned_times.py — a time a device sends must name its zone (ZonedDateTimeField,
apps/core/api/times.py; 03 §5.10).

    "2026-11-10T04:50:00Z"        accepted: 04:50 in UTC
    "2026-11-10T07:50:00+03:00"   accepted: the same moment, written in Arusha's time
    "2026-11-10T07:50:00"         refused: which 07:50? Read as UTC, it would be 3 hours late in Arusha

Pure: no database. Fake data only: the repo is public.
"""

import datetime as dt
from typing import Any

import pytest
from rest_framework import serializers

from apps.core.api.times import ZonedDateTimeField

FOUR_FIFTY_UTC = dt.datetime(2026, 11, 10, 4, 50, tzinfo=dt.UTC)


class _Report(serializers.Serializer[Any]):
    at = ZonedDateTimeField()


def _read(value: object) -> serializers.Serializer[Any]:
    report = _Report(data={"at": value})
    report.is_valid()
    return report


@pytest.mark.parametrize("written", ["2026-11-10T04:50:00Z", "2026-11-10T07:50:00+03:00", "2026-11-10T04:50:00+00:00"])
def test_a_time_with_its_zone_is_read_as_that_moment(written: str) -> None:
    assert _read(written).validated_data["at"] == FOUR_FIFTY_UTC


@pytest.mark.parametrize(
    "written",
    ["2026-11-10T07:50:00", "2026-11-10 07:50", "2026-11-10", dt.datetime(2026, 11, 10, 7, 50)],
    ids=["text", "text_with_a_space", "a_day_alone", "a_python_time"],
)
def test_a_time_with_no_zone_is_refused(written: object) -> None:
    # DRF alone would read each in the server's zone, UTC: a laptop in Arusha that wrote its own 07:50 would be read as
    # 10:50 there, and its clock-ins flagged for it (ATT-1's review). Refused with DRF's own code for a time written
    # wrong, as it is a bug in the device's code, not a person's mistake.
    [refusal] = _read(written).errors["at"]
    assert refusal.code == "invalid"


@pytest.mark.parametrize("written", ["today", "2026-13-40T07:50:00Z", 7])
def test_what_is_no_time_at_all_gets_drfs_own_answer(written: object) -> None:
    assert _read(written).errors["at"][0].code == "invalid"
