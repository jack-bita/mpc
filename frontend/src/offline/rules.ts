// rules.ts — which value of a shop's rule is in force on a day, worked out on the laptop from the rows it
// pulled (SYNC-7, 02 §5, 03 §5.8). Pure calculations: no database, no clock, so each case is a plain test.
//
// The same answer the server's get_setting gives (apps/shops/selectors.py), so a laptop offline locks its
// screen after the same minutes, and so on, as the office would say.
import type { components } from "@/api/schema";

type SettingRow = components["schemas"]["SettingRecord"];
type SettingKey = components["schemas"]["SettingKeyRecord"];

/**
 * The shop's date at a moment, as "2026-11-11": the day in the shop's own time zone, never the laptop's.
 * A laptop's clock may be set to any zone, and a rule starts on the shop's day (D: Arusha's midnight).
 * `at` is milliseconds since 1970, already put right by the server's clock offset.
 */
export function shopToday(timezone: string, at: number): string {
  // en-CA is chosen only for its parts' order; each part is read by name, so no locale's format leaks in.
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: timezone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(at);
  const part = (type: string) =>
    parts.find((each) => each.type === type)?.value ?? "";
  return `${part("year")}-${part("month")}-${part("day")}`;
}

/**
 * A rule's value, as stored text, on `day`, for a side or for the whole shop (side null):
 * 1. the side's own row that started last, on or before the day;
 * 2. else the shop's row that started last, on or before the day;
 * 3. else the rule's default.
 * A side's row beats even a newer shop row (CORE-4): the side chose its own value on purpose. Only
 * for a rule a side may set (scope "side"): a shop-wide rule goes straight to the shop's row, as
 * get_setting does. The server sends no side row of a shop-wide rule; this keeps the two agreeing even
 * if one slipped through.
 *
 * A same-day fix is settled before this runs: the laptop holds one row per rule, side and day, the last
 * one it was given (pull.ts, applySetting). Never by the row's id, which the manager's browser made, so its
 * order follows that browser's clock, not the order the server saved the rows in.
 *
 * Days compare as text: "2026-11-01" < "2026-11-11", as ISO dates sort as they read.
 */
export function ruleInForce(
  rows: readonly SettingRow[],
  rule: SettingKey,
  side: string | null,
  day: string,
): string {
  const ofSide =
    side !== null && rule.scope === "side"
      ? latest(rows, rule.key, side, day)
      : undefined;
  const ofShop = latest(rows, rule.key, null, day);
  return (ofSide ?? ofShop)?.value ?? rule.default;
}

function latest(
  rows: readonly SettingRow[],
  key: string,
  side: string | null,
  day: string,
): SettingRow | undefined {
  let best: SettingRow | undefined;
  for (const row of rows) {
    if (row.key !== key || row.side !== side || row.effective_from > day)
      continue;
    // One row per day (see above), so a later start day is all that decides.
    if (best === undefined || row.effective_from > best.effective_from)
      best = row;
  }
  return best;
}
