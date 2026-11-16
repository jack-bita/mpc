// settings.ts — a made-up answer of GET /api/v1/shops/settings/ for the settings page's tests (SHOP-5): every
// rule of the registry, with its default as its value, and builders for a rule's line and a row. Tests only.
// Fake data: the made-up MPC of devices.ts, its Dawa and Vyakula sides, and made-up nicknames.
import type { components } from "@/api/schema";

import { DAWA, VYAKULA, whoIsHere } from "./devices";

type RuleLine = components["schemas"]["RuleAnswer"];
type RuleRow = components["schemas"]["Setting"];

/** The shop's today in these answers: Sunday 15 Nov 2026. */
export const TODAY = "2026-11-15";

let rows = 0;

/** A rule's row, the late fine's unless told otherwise, set by Neema on the shop's today. Each its own id. */
export function row(fields: Partial<RuleRow> = {}): RuleRow {
  rows += 1;
  return {
    id: `019a8100-0000-7000-8000-${String(rows).padStart(12, "0")}`,
    key: "attendance.late_fine",
    side: null,
    value: "1000.00",
    effective_from: TODAY,
    note: "",
    set_by: "Neema",
    created_at: "2026-11-15T07:00:00Z",
    ...fields,
  };
}

/** One line of the answer: the late fine's, unless told otherwise, with a made-up default of 1,000: a value with
 * thousands to write, where the registry's own is 0 (ATT-2). */
export function line(fields: Partial<RuleLine> = {}): RuleLine {
  return {
    key: "attendance.late_fine",
    kind: "money",
    scope: "shop",
    side: null,
    default: "1000.00",
    value: fields.default ?? "1000.00",
    rows: [],
    ...fields,
  };
}

/** A shop's rule at its default: one line. */
function shopRule(
  key: RuleLine["key"],
  kind: RuleLine["kind"],
  value: string,
): RuleLine {
  return line({ key, kind, scope: "shop", side: null, default: value, value });
}

/** A side's rule at its default: a line for Dawa, then one for Vyakula, by the sides' letters (D, F). */
function sideRule(
  key: RuleLine["key"],
  kind: RuleLine["kind"],
  value: string,
): RuleLine[] {
  return [DAWA, VYAKULA].map((side) =>
    line({ key, kind, scope: "side", side: side.id, default: value, value }),
  );
}

/** Every rule of the registry, in its order, at its default, as the server sends them before anyone sets one. */
export const SHOP_RULES: components["schemas"]["ShopRulesAnswer"] = {
  today: TODAY,
  rules: [
    shopRule("attendance.enabled", "yes_no", "false"),
    shopRule("attendance.on_time_until", "time", "07:35"),
    // No fine until the owner types one (ATT-2).
    shopRule("attendance.late_fine", "money", "0.00"),
    shopRule("attendance.second_fine_from", "time", "08:00"),
    shopRule("attendance.second_fine", "money", "0.00"),
    shopRule("attendance.review_from", "time", "08:30"),
    shopRule("attendance.afternoon_from", "time", "12:00"),
    shopRule("attendance.midday", "time", "13:00"),
    shopRule("attendance.morning_leave_until", "time", "13:30"),
    shopRule("attendance.closing", "time", "18:40"),
    shopRule("money.rounding_step", "money", "1.00"),
    shopRule("session.idle_minutes", "whole", "15"),
    ...sideRule("cash.tolerance", "money", "0.00"),
    ...sideRule("count.tolerance_pct", "percent", "0.00"),
    ...sideRule("expiry.alert_days", "whole", "90"),
    ...sideRule("stock.block_negative", "yes_no", "false"),
  ],
};

/** The same answer with one line replaced, found by its key and its side: a shop's rule's line, or one side's line of
 * a side's rule. */
export function withRule(
  changed: RuleLine,
): components["schemas"]["ShopRulesAnswer"] {
  return {
    ...SHOP_RULES,
    rules: SHOP_RULES.rules.map((each) =>
      each.key === changed.key && each.side === changed.side ? changed : each,
    ),
  };
}

/** The owner, as `me` answers for him: settings.manage on the whole shop, which the server also counts on every side
 * (HeldPermissions.on), so both lists hold it. */
export const OWNER: components["schemas"]["WhoIsHere"] = {
  ...whoIsHere([]),
  permissions: {
    whole_shop: ["settings.manage"],
    sides: [
      { ...DAWA, permissions: ["settings.manage"] },
      { ...VYAKULA, permissions: ["settings.manage"] },
    ],
  },
};
