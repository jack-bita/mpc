// closures.test.ts — the day before a day, as a moved last day's box reaches back to it (ATT-9): across a month's end,
// a year's, and a leap day.
import { describe, expect, it } from "vitest";

import { dayBefore } from "./closures";

describe("dayBefore", () => {
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
