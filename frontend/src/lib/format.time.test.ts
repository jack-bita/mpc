// format.time.test.ts — a time of day as the shop reads it: "07:55", 24 hours, in the shop's own zone, like
// a phone's clock and the shop's rules ("late after 08:00"), never Swahili time (Jack, SYNC-11).
import { describe, expect, it } from "vitest";

import { formatTime } from "./format";

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
