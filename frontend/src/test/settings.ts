// settings.ts — a made-up answer of GET /api/v1/shops/settings/ for the settings page's tests (SHOP-5): every
// rule of the registry, with its default as its value, and builders for a rule's line and a row. Tests only.
// Fake data: the made-up MPC of devices.ts, its Dawa and Vyakula sides, and made-up nicknames.
import type { components } from "@/api/schema";

import { DAWA, VYAKULA } from "./devices";

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

/** One line of the answer: the late fine's, at its default, unless told otherwise. */
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
    shopRule("attendance.on_time_until", "time", "07:35"),
    shopRule("attendance.late_fine", "money", "1000.00"),
    shopRule("money.rounding_step", "money", "1.00"),
    shopRule("session.idle_minutes", "whole", "15"),
    ...sideRule("cash.tolerance", "money", "0.00"),
    ...sideRule("count.tolerance_pct", "percent", "0.00"),
    ...sideRule("expiry.alert_days", "whole", "90"),
    ...sideRule("stock.block_negative", "yes_no", "false"),
  ],
};

/** The same answer with one shop's rule's line replaced, found by its key. */
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
