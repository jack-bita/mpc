// attendance-month.test.ts — the months as the month page counts them (ATT-5): the month of a day, the month before
// and after, across a year's end, and what the address may name as a month.
import { describe, expect, it } from "vitest";

import { isMonth, monthAfter, monthBefore, monthOf } from "./attendance-month";

describe("the months of the month page", () => {
  it("names the month of a day", () => {
    expect(monthOf("2026-11-20")).toBe("2026-11");
    expect(monthOf("2027-01-01")).toBe("2027-01");
  });

  it("steps a month back and forward, across a year's end", () => {
    expect(monthBefore("2026-11")).toBe("2026-10");
    expect(monthBefore("2027-01")).toBe("2026-12");
    expect(monthAfter("2026-11")).toBe("2026-12");
    expect(monthAfter("2026-12")).toBe("2027-01");
  });

  it("takes only a month as the address writes one", () => {
    // Anything else in the address is ignored, and the page opens this month: a typo, a day, a 13th month.
    expect(isMonth("2026-11")).toBe(true);
    expect(isMonth("2000-01")).toBe(true);
    for (const wrong of [
      "2026-13",
      "2026-00",
      "2026-1",
      "2026-11-20",
      "Novemba",
      "",
      // Before the first month the server takes: the page opens this month, not its refusal (ATT-12's review).
      "1999-12",
      "0001-01",
    ]) {
      expect(isMonth(wrong)).toBe(false);
    }
  });
});
