// rules.ts — the shop's rules as the settings page lays them out (SHOP-5): grouped by area, a side's rule
// with one line per side, and, for each line, the row in force on a day and the rows still to come.
//
// GET /api/v1/shops/settings/ sends every rule of the registry, in its order: a shop's rule once, a side's
// rule once for each side the person sees, each with its value today and its rows, newest first (SHOP-3). The
// value today is the server's, worked out by get_setting itself, so the page never disagrees with the pay run.
// The rows still to come, and which row is the one in use, are read here from the same rows, by the same
// rule as get_setting's (backend/apps/shops/selectors.py): on a day, the side's own row that has started wins,
// even an older one; else the shop's; else the default. A shop row on a side's line is one only code that skips
// set_setting could write; it shows, marked as the shop's, so the page never hides why a value is so.
//
// Days are the server's "2026-12-01", compared as text: that form sorts as the days do. "Today" is the shop's
// today, as the server sends it (`today`), never this device's clock, which may be wrong or in another zone.
import type { components } from "@/api/schema";

import {
  type Area,
  AREAS,
  isKnownKey,
  RULE_AREA,
  type SettingKey,
} from "./setting-words";

export type ShopRules = components["schemas"]["ShopRulesAnswer"];
export type RuleLine = components["schemas"]["RuleAnswer"];
export type RuleRow = components["schemas"]["Setting"];

/** One rule on the page: its key, and its lines, one for a shop's rule, one per side for a side's. */
export interface RuleOnPage {
  key: SettingKey;
  lines: RuleLine[];
}

/** One area of the page, with its rules in the registry's order. */
export interface AreaOnPage {
  area: Area;
  rules: RuleOnPage[];
}

/** The rules by area, in the page's order of areas and the registry's order within each. A key the app has no
 * words for, a newer server's, is left out until the app is updated (setting-words.ts). An area with no rule
 * the person sees is left out too. */
export function rulesByArea(rules: readonly RuleLine[]): AreaOnPage[] {
  // By key, in the order the keys first come: a side's lines come one after the other, side by side.
  const byKey = new Map<SettingKey, RuleLine[]>();
  for (const line of rules) {
    if (!isKnownKey(line.key)) continue;
    const lines = byKey.get(line.key);
    if (lines) lines.push(line);
    else byKey.set(line.key, [line]);
  }
  const all = [...byKey].map(([key, lines]) => ({ key, lines }));
  return AREAS.map((area) => ({
    area,
    rules: all.filter((rule) => RULE_AREA[rule.key] === area),
  })).filter((area) => area.rules.length > 0);
}

/** The row in force on `day`, by get_setting's rule, or null when the default is. */
export function rowInForce(line: RuleLine, day: string): RuleRow | null {
  // Newest first already, with get_setting's tie-break: on one day, the row written last comes first.
  const started = line.rows.filter((row) => row.effective_from <= day);
  // A side's own row beats the shop's, even an older one (02 §4). On a shop's line every row is the shop's.
  return (
    started.find((row) => row.side !== null) ??
    started.find((row) => row.side === null) ??
    null
  );
}

/** The rows still to come after `today`, soonest first: each one that will be in force from its own day. A row
 * that never will, as a second row written later for the same day, or a shop's row on a side whose own row
 * goes on winning, is left out, so the page never announces a value that won't come. */
export function rowsToCome(line: RuleLine, today: string): RuleRow[] {
  const days = [
    ...new Set(
      line.rows.map((row) => row.effective_from).filter((day) => day > today),
    ),
  ].sort();
  return days
    .map((day) => rowInForce(line, day))
    .filter(
      (row, index): row is RuleRow => row?.effective_from === days[index],
    );
}
