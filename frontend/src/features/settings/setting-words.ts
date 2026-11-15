// setting-words.ts — each of the shop's rules as the settings page shows it: its area, its name, its line of
// help, and its value written the way people read it (SHOP-5, ADR-0040).
//
// The server sends a rule by its key, "attendance.late_fine", never by a sentence: its registry's description
// is for developers (backend/apps/core/settings_registry.py). The words live in the books, under
// shopSettings.rules, nested by the key's dots as the error codes are (errors.pin.locked): a rule's `name`, its
// `help`, and `shown`, its value in a sentence ("Dakika {value}"), as a count needs its unit and money doesn't.
//
// The keys are a fixed list in the API's description (SettingKeyEnum). RULE_AREA is a Record of every one of
// them, so a key a later card adds to the registry (ATT-2's) fails `pnpm typecheck` here until it has an area,
// and the typed t() below fails it until both books hold its words; setting-words.test.ts walks the books too.
// Once it has both, the page shows it by itself.
//
// "use client": it asks use-intl for words (use-client.test.ts).
"use client";

import { useTranslations } from "use-intl";

import type { components } from "@/api/schema";
import { Decimal } from "@/lib/decimal";
import { clockPart, formatMoneyExact, formatQuantity } from "@/lib/format";

export type SettingKey = components["schemas"]["SettingKeyEnum"];
export type SettingKind = components["schemas"]["SettingKindEnum"];

/** The page's areas, in the order it shows them: the rules people ask about first come first. */
export const AREAS = ["attendance", "money", "computers", "stock"] as const;
export type Area = (typeof AREAS)[number];

/** Each rule's area, by its key. Not read from the key's first part: the drawer's tolerance (`cash.`) sits
 * with money, and the stock count's (`count.`) with the stock, where the owner looks for them. */
export const RULE_AREA: Record<SettingKey, Area> = {
  "attendance.on_time_until": "attendance",
  "attendance.late_fine": "attendance",
  "money.rounding_step": "money",
  "cash.tolerance": "money",
  "session.idle_minutes": "computers",
  "count.tolerance_pct": "stock",
  "expiry.alert_days": "stock",
  "stock.block_negative": "stock",
};

/** Every key the app has words for. */
export const RULE_KEYS = Object.keys(RULE_AREA) as SettingKey[];

/** Whether the app knows a key. The server's answer types every key as one of the schema's, but a newer
 * server can meet an older app, as a laptop may run an old version for days (03 §6.5). */
export function isKnownKey(key: string): key is SettingKey {
  return Object.hasOwn(RULE_AREA, key);
}

/** A rule's name, its help, and a value of its kind as people read it, in the open language. */
export function useRuleWords() {
  const t = useTranslations("shopSettings");
  // The clock-in's way of writing a time of day: "07:35 asubuhi" in Swahili, "07:35" in English (SYNC-11).
  const attendance = useTranslations("attendance");

  /** A value of `kind`, as the server writes it ("1000.00", "07:35", "true"), as people read it. */
  function written(kind: SettingKind, value: string): string {
    switch (kind) {
      // Exactly, cents and all if a rule has them: the page shows what is saved (format.ts).
      case "money":
        return formatMoneyExact(new Decimal(value));
      // "5.00" as "5", "1440" as "1,440": the zeros at the end left off, a comma between thousands.
      case "percent":
      case "whole":
        return formatQuantity(new Decimal(value));
      case "time":
        return attendance("timeOfDay", { time: value, part: clockPart(value) });
      case "yes_no":
        return value === "true" ? t("yes") : t("no");
    }
  }

  return {
    name: (key: SettingKey) => t(`rules.${key}.name`),
    help: (key: SettingKey) => t(`rules.${key}.help`),
    /** The value in the rule's own sentence: "Dakika 15", "Siku 90", "TSh 1,000". */
    shown: (key: SettingKey, kind: SettingKind, value: string) =>
      t(`rules.${key}.shown`, { value: written(kind, value) }),
    area: (area: Area) => t(`areas.${area}`),
  };
}
