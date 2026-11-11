// rules.test.ts — a rule's value on a day, as the server's get_setting gives it (SYNC-7, 02 §5), and the
// shop's day in its own time zone.
import { describe, expect, it } from "vitest";

import type { components } from "@/api/schema";
import { DAWA, VYAKULA } from "@/test/devices";
import { IDLE_15, IDLE_RULE } from "@/test/shop-lists";

import { ruleInForce, shopToday } from "./rules";

type SettingRow = components["schemas"]["SettingRecord"];

// Rows of the idle lock, each made up: its id (in the order the server wrote them), side, start and value.
function row(
  idEnd: string,
  side: string | null,
  from: string,
  value: string,
): SettingRow {
  return {
    id: `019a5e00-0000-7000-8000-000000000${idEnd}`,
    key: IDLE_RULE.key,
    side,
    effective_from: from,
    value,
  };
}

const TODAY = "2026-11-11";

describe("the rule in force", () => {
  it("is the default when the shop has no row", () => {
    expect(ruleInForce([], IDLE_RULE, null, TODAY)).toBe("10");
  });

  it("is the shop's row that started last, on or before the day", () => {
    const rows = [
      IDLE_15, // from 1 November
      row("102", null, "2026-11-05", "20"),
      row("103", null, "2026-11-20", "30"), // not yet
    ];

    expect(ruleInForce(rows, IDLE_RULE, null, TODAY)).toBe("20");
  });

  it("starts on its first day", () => {
    expect(ruleInForce([IDLE_15], IDLE_RULE, null, "2026-11-01")).toBe("15");
    expect(ruleInForce([IDLE_15], IDLE_RULE, null, "2026-10-31")).toBe("10");
  });

  it("is the side's own row before the shop's, even a newer shop row", () => {
    const rows = [
      row("102", DAWA.id, "2026-11-02", "5"),
      row("103", null, "2026-11-09", "30"),
    ];

    expect(ruleInForce(rows, IDLE_RULE, DAWA.id, TODAY)).toBe("5");
    // Another side has no row of its own: the shop's.
    expect(ruleInForce(rows, IDLE_RULE, VYAKULA.id, TODAY)).toBe("30");
    // The whole shop never reads a side's row.
    expect(ruleInForce(rows, IDLE_RULE, null, TODAY)).toBe("30");
  });

  it("falls back to the shop's row while the side's starts later", () => {
    const rows = [IDLE_15, row("102", DAWA.id, "2026-11-20", "5")];

    expect(ruleInForce(rows, IDLE_RULE, DAWA.id, TODAY)).toBe("15");
  });

  it("reads only its own rule's rows", () => {
    const other = { ...IDLE_15, key: "drawer.float", value: "50000" };

    expect(ruleInForce([other], IDLE_RULE, null, TODAY)).toBe("10");
  });
});

describe("the shop's day", () => {
  it("is the day in the shop's zone, not the laptop's", () => {
    // 22:30 in London on 10 November is 01:30 on 11 November in Arusha (UTC+3).
    const lateEvening = Date.parse("2026-11-10T22:30:00Z");

    expect(shopToday("Africa/Dar_es_Salaam", lateEvening)).toBe("2026-11-11");
    expect(shopToday("Europe/London", lateEvening)).toBe("2026-11-10");
  });
});
