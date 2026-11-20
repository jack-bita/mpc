// worker-month.test.ts — a worker's month as the calendar counts it (ATT-12): the weeks of a month, Monday first, with
// empty places before the 1st and after the last, and the address a name on the month page opens.
import { describe, expect, it } from "vitest";

import { calendarWeeks, workerMonthAddress } from "./worker-month";

describe("the weeks of a worker's calendar", () => {
  it("starts November 2026, whose 1st is a Sunday, in the week's last place", () => {
    const weeks = calendarWeeks("2026-11");
    expect(weeks).toHaveLength(6);
    expect(weeks[0]).toEqual([
      null,
      null,
      null,
      null,
      null,
      null,
      "2026-11-01",
    ]);
    expect(weeks[2]).toEqual([
      "2026-11-09",
      "2026-11-10",
      "2026-11-11",
      "2026-11-12",
      "2026-11-13",
      "2026-11-14",
      "2026-11-15",
    ]);
    expect(weeks[5]).toEqual([
      "2026-11-30",
      null,
      null,
      null,
      null,
      null,
      null,
    ]);
  });

  it("starts a month whose 1st is a Monday in the first place, with no empty week", () => {
    // 1 February 2027 is a Monday, and the month has 28 days: four whole weeks.
    const weeks = calendarWeeks("2027-02");
    expect(weeks).toHaveLength(4);
    expect(weeks[0]?.[0]).toBe("2027-02-01");
    expect(weeks[3]?.[6]).toBe("2027-02-28");
  });

  it("counts a leap year's February", () => {
    // 2028 is a leap year: 29 February is a Tuesday.
    expect(calendarWeeks("2028-02").flat().filter(Boolean)).toHaveLength(29);
  });

  it("keeps every week to seven places", () => {
    for (const month of ["2026-10", "2026-11", "2026-12", "2027-01"]) {
      expect(calendarWeeks(month).every((week) => week.length === 7)).toBe(
        true,
      );
    }
  });
});

describe("a worker's month's address", () => {
  it("names the worker's job and the month", () => {
    expect(
      workerMonthAddress("019a8400-0000-7000-8000-000000000001", "2026-11"),
    ).toBe(
      "/attendance-month/worker/?staff=019a8400-0000-7000-8000-000000000001&month=2026-11",
    );
  });
});
