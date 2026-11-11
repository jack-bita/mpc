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
 * A side's row beats even a newer shop row (CORE-4): the side chose its own value on purpose.
 *
 * Two rows of one rule, side and start day: a same-day fix. The fix is the one written last, and the
 * last one the laptop was given (SYNC-3's note). Row ids are UUIDv7, which sort in the order the server
 * made them, so the greatest id is the fix: the order the laptop got them in isn't kept by IndexedDB.
 *
 * Days compare as text: "2026-11-01" < "2026-11-11", as ISO dates sort as they read.
 */
export function ruleInForce(
  rows: readonly SettingRow[],
  rule: SettingKey,
  side: string | null,
  day: string,
): string {
  const ofSide = side === null ? undefined : latest(rows, rule.key, side, day);
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
    if (
      best === undefined ||
      row.effective_from > best.effective_from ||
      (row.effective_from === best.effective_from && row.id > best.id)
    )
      best = row;
  }
  return best;
}
