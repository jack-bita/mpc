// format.time.test.ts — a time of day and a date as the shop reads them: "07:55", 24 hours, in the shop's own
// zone, like a phone's clock and the shop's rules ("late after 08:00"), never Swahili time (Jack, SYNC-11); and
// "13/11/2026", day, month, year, the order Tanzania writes a date in.
import { describe, expect, it } from "vitest";

import { dayPart, formatDate, formatTime } from "./format";

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
