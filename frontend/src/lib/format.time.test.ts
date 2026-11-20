// format.time.test.ts — a time of day and a date as the shop reads them: "07:55", 24 hours, in the shop's own
// zone, like a phone's clock and the shop's rules ("late after 08:00"), never Swahili time (Jack, SYNC-11); and
// "13/11/2026", day, month, year, the order Tanzania writes a date in. And a day with no time: the day before it, its
// day and month alone, "12/11", and its weekday, none moved by a zone (ATT-9, ATT-5).
import { describe, expect, it } from "vitest";

import {
  clockPart,
  dayBefore,
  dayPart,
  formatDate,
  formatDay,
  formatDayMonth,
  formatTime,
  weekdayOf,
} from "./format";

const DAR = "Africa/Dar_es_Salaam";

describe("a time of day", () => {
  it("reads in the shop's zone, whatever zone the laptop is set to", () => {
    // Dar is 3 hours ahead of UTC.
    expect(formatTime("2026-11-13T04:55:00.000Z", DAR)).toBe("07:55");
  });

  it("counts 24 hours, with no a.m. or p.m.", () => {
    expect(formatTime("2026-11-13T15:02:00.000Z", DAR)).toBe("18:02");
  });

  it("writes five past midnight as 00:05, never 24:05", () => {
    // Some browsers write midnight as 24 with a 24-hour clock; h23 counts 0 to 23.
    expect(formatTime("2026-11-12T21:05:00.000Z", DAR)).toBe("00:05");
  });
});

describe("a date", () => {
  it("reads day, month, year, the Tanzanian way", () => {
    expect(formatDate("2026-11-13T04:55:00.000Z", DAR)).toBe("13/11/2026");
  });

  it("is the shop's date: 22:30 UTC on the 12th is already the 13th in Dar", () => {
    expect(formatDate("2026-11-12T22:30:00.000Z", DAR)).toBe("13/11/2026");
  });
});

describe("the part of the day", () => {
  // Swahili screens name it after the time, "saa 07:55 asubuhi", so nobody reads 07:55 as Swahili time
  // (saa saba is 13:00) (Jack, SYNC-11). By the shop's clock: Dar is 3 hours ahead of UTC.
  it.each([
    ["2026-11-13T02:00:00.000Z", "morning"], // 05:00, the first minute of asubuhi
    ["2026-11-13T04:55:00.000Z", "morning"], // 07:55
    ["2026-11-13T08:59:00.000Z", "morning"], // 11:59
    ["2026-11-13T09:00:00.000Z", "afternoon"], // 12:00, mchana
    ["2026-11-13T12:59:00.000Z", "afternoon"], // 15:59
    ["2026-11-13T13:00:00.000Z", "evening"], // 16:00, jioni
    ["2026-11-13T15:02:00.000Z", "evening"], // 18:02
    ["2026-11-13T15:59:00.000Z", "evening"], // 18:59
    ["2026-11-13T16:00:00.000Z", "night"], // 19:00, usiku
    ["2026-11-13T20:50:00.000Z", "night"], // 23:50
    ["2026-11-13T01:59:00.000Z", "night"], // 04:59
  ])("puts %s in the %s", (at, part) => {
    expect(dayPart(at, DAR)).toBe(part);
  });
});

describe("a day with no time (SHOP-5)", () => {
  it("reads day, month, year, as formatDate writes a date", () => {
    // The day a rule's new value starts on, as the server sends it.
    expect(formatDay("2026-12-01")).toBe("01/12/2026");
  });

  it("keeps its day in a zone behind UTC", () => {
    // Through a Date, "2026-12-01" is midnight UTC, which is still 30 November in Lima. A day has no zone.
    const lima = new Intl.DateTimeFormat("en-GB", { timeZone: "America/Lima" });
    expect(lima.format(Date.parse("2026-12-01"))).toBe("30/11/2026");
    expect(formatDay("2026-12-01")).toBe("01/12/2026");
  });
});

describe("the day before a day (ATT-9)", () => {
  it.each([
    ["2026-11-15", "2026-11-14"],
    ["2026-12-01", "2026-11-30"],
    ["2027-01-01", "2026-12-31"],
    ["2028-03-01", "2028-02-29"],
    ["2027-03-01", "2027-02-28"],
  ])("the day before %s is %s", (day, before) => {
    expect(dayBefore(day)).toBe(before);
  });
});

describe("a day's day and month, and its weekday (ATT-5)", () => {
  it("writes the day and the month alone, as a month page's line does", () => {
    // "Juma · Alhamisi 12/11 · hakuna Toka": the year is the month's, said above the list.
    expect(formatDayMonth("2026-11-12")).toBe("12/11");
    expect(formatDayMonth("2027-01-05")).toBe("05/01");
  });

  it("names its weekday as JavaScript numbers them, Sunday 0, whatever the phone's zone", () => {
    // Thursday 12 November 2026; Sunday 1 November; Saturday 31 December 2022. A day has no zone: in Lima, midnight
    // UTC of the 12th is still the 11th, so the weekday is never read through the phone's own clock.
    expect(weekdayOf("2026-11-12")).toBe(4);
    expect(weekdayOf("2026-11-01")).toBe(0);
    expect(weekdayOf("2022-12-31")).toBe(6);
  });
});

describe("the part of the day of a clock time (SHOP-5)", () => {
  // A rule's time of day, attendance.on_time_until, in the same parts as dayPart's.
  it.each([
    ["05:00", "morning"],
    ["07:35", "morning"],
    ["12:00", "afternoon"],
    ["16:00", "evening"],
    ["19:00", "night"],
    ["04:59", "night"],
  ])("puts %s in the %s", (clock, part) => {
    expect(clockPart(clock)).toBe(part);
  });
});
