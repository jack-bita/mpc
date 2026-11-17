// rules.test.ts — the settings page's layout of the rules, and which row is in force on a day, by the same rule
// as the server's get_setting (SHOP-5): the side's own row, then the shop's, then the default.
import { describe, expect, it } from "vitest";

import { DAWA, VYAKULA } from "@/test/devices";
import { line, row, SHOP_RULES } from "@/test/settings";

import { rowInForce, rowsToCome, rulesByArea } from "./rules";

const TODAY = "2026-11-15";

describe("the rules by area", () => {
  it("puts every rule in its area, in the page's order, a side's rule with a line per side", () => {
    const page = rulesByArea(SHOP_RULES.rules);

    expect(page.map((area) => area.area)).toEqual([
      "attendance",
      "money",
      "computers",
      "stock",
    ]);
    expect(
      page.map((area) =>
        area.rules.map((rule) => [rule.key, rule.lines.length]),
      ),
    ).toEqual([
      [
        ["attendance.enabled", 1],
        ["attendance.on_time_until", 1],
        ["attendance.late_fine", 1],
        ["attendance.second_fine_from", 1],
        ["attendance.second_fine", 1],
        ["attendance.review_from", 1],
        ["attendance.afternoon_from", 1],
        ["attendance.midday", 1],
        ["attendance.morning_leave_until", 1],
        ["attendance.closing", 1],
      ],
      [
        ["money.rounding_step", 1],
        ["cash.tolerance", 2],
      ],
      [["session.idle_minutes", 1]],
      [
        ["count.tolerance_pct", 2],
        ["expiry.alert_days", 2],
        ["stock.block_negative", 2],
      ],
    ]);
  });

  it("leaves out a key the app has no words for yet, as a newer server's", () => {
    const newer = line({
      key: "attendance.half_day_after" as never,
      value: "11:00",
    });

    const page = rulesByArea([...SHOP_RULES.rules, newer]);

    const keys = page.flatMap((area) => area.rules.map((rule) => rule.key));
    expect(keys).not.toContain("attendance.half_day_after");
    expect(keys).toHaveLength(16);
  });

  it("leaves out an area with no rule the person sees", () => {
    const page = rulesByArea(
      SHOP_RULES.rules.filter((each) => each.key.startsWith("attendance.")),
    );

    expect(page.map((area) => area.area)).toEqual(["attendance"]);
  });
});

describe("the row in force on a day", () => {
  it("is the newest row that has started, and none before the first", () => {
    const fine = line({
      rows: [
        row({ value: "2000.00", effective_from: "2026-12-01" }),
        row({ value: "1500.00", effective_from: "2026-11-01" }),
      ],
    });

    expect(rowInForce(fine, TODAY)?.value).toBe("1500.00");
    expect(rowInForce(fine, "2026-12-01")?.value).toBe("2000.00");
    // Before the first row, the default is in force.
    expect(rowInForce(fine, "2026-10-31")).toBeNull();
  });

  it("is the side's own row over the shop's, even an older one, as get_setting decides", () => {
    // A shop row on a side's line, which only code that skips set_setting could write.
    const tolerance = line({
      key: "cash.tolerance",
      scope: "side",
      side: DAWA.id,
      rows: [
        row({
          key: "cash.tolerance",
          side: null,
          value: "500.00",
          effective_from: "2026-11-10",
        }),
        row({
          key: "cash.tolerance",
          side: DAWA.id,
          value: "200.00",
          effective_from: "2026-11-01",
        }),
      ],
    });

    expect(rowInForce(tolerance, TODAY)?.value).toBe("200.00");
  });

  it("is the shop's row on a side with none of its own", () => {
    const tolerance = line({
      key: "cash.tolerance",
      scope: "side",
      side: VYAKULA.id,
      rows: [
        row({
          key: "cash.tolerance",
          side: null,
          value: "500.00",
          effective_from: "2026-11-10",
        }),
      ],
    });

    expect(rowInForce(tolerance, TODAY)?.value).toBe("500.00");
  });
});

describe("the rows still to come", () => {
  it("are the rows after today, soonest first", () => {
    const fine = line({
      rows: [
        row({ value: "3000.00", effective_from: "2027-01-01" }),
        row({ value: "2000.00", effective_from: "2026-12-01" }),
        row({ value: "1500.00", effective_from: "2026-11-01" }),
      ],
    });

    expect(rowsToCome(fine, TODAY).map((each) => each.value)).toEqual([
      "2000.00",
      "3000.00",
    ]);
  });

  it("start tomorrow at the soonest: a row from today is in force, not to come", () => {
    const fine = line({
      rows: [row({ value: "2000.00", effective_from: TODAY })],
    });

    expect(rowsToCome(fine, TODAY)).toEqual([]);
    expect(rowInForce(fine, TODAY)?.value).toBe("2000.00");
  });

  it("are only the last written of one day, as that one is in force", () => {
    // The owner typed 2,000, then fixed it to 2,500 for the same day: a fix is a new row (T2).
    const fine = line({
      rows: [
        row({
          value: "2500.00",
          effective_from: "2026-12-01",
          created_at: "2026-11-15T10:05:00Z",
        }),
        row({
          value: "2000.00",
          effective_from: "2026-12-01",
          created_at: "2026-11-15T10:00:00Z",
        }),
      ],
    });

    expect(rowsToCome(fine, TODAY).map((each) => each.value)).toEqual([
      "2500.00",
    ]);
  });

  it("leave out a shop's row a side's own row goes on beating", () => {
    const tolerance = line({
      key: "cash.tolerance",
      scope: "side",
      side: DAWA.id,
      rows: [
        row({
          key: "cash.tolerance",
          side: null,
          value: "500.00",
          effective_from: "2026-12-01",
        }),
        row({
          key: "cash.tolerance",
          side: DAWA.id,
          value: "200.00",
          effective_from: "2026-11-01",
        }),
      ],
    });

    expect(rowsToCome(tolerance, TODAY)).toEqual([]);
  });
});
