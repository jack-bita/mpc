// setting-words.test.ts — every rule the app knows has its words in both books, and every area its name
// (SHOP-5, ADR-0040), as errors.test.ts walks every code the API sends.
//
// `pnpm typecheck` already fails for a key of the schema with no area (RULE_AREA is a Record of them all),
// and for a sentence the Swahili book lacks (the books' keys are typed as Swahili's). This walks both books
// by hand as well, so English can't lack one either, and nothing says "shopSettings.rules…" on a screen.
import { describe, expect, it } from "vitest";

import { LANGUAGES, MESSAGES } from "@/i18n/language";
import { sentences } from "@/test/language";

import { AREAS, isKnownKey, RULE_AREA, RULE_KEYS } from "./setting-words";

// Each rule's three sentences: its name, its line of help, and its value in a sentence.
const PARTS = ["name", "help", "shown"] as const;

describe("the rules' words", () => {
  it("know the sixteen rules of the registry", () => {
    // The registry as ATT-2 left it (backend/apps/core/settings_registry.py): SHOP-3's eight and the attendance
    // day's eight more. A new key reaches this list through RULE_AREA, which typecheck makes it join once the
    // schema names it.
    expect(RULE_KEYS).toEqual([
      "attendance.enabled",
      "attendance.on_time_until",
      "attendance.late_fine",
      "attendance.second_fine_from",
      "attendance.second_fine",
      "attendance.review_from",
      "attendance.afternoon_from",
      "attendance.midday",
      "attendance.morning_leave_until",
      "attendance.closing",
      "money.rounding_step",
      "cash.tolerance",
      "session.idle_minutes",
      "count.tolerance_pct",
      "expiry.alert_days",
      "stock.block_negative",
    ]);
  });

  it.each(LANGUAGES)(
    "%s: every rule has a name, a line of help and its value's sentence",
    (language) => {
      const book = sentences(MESSAGES[language]);
      const missing = RULE_KEYS.flatMap((key) =>
        PARTS.map((part) => `shopSettings.rules.${key}.${part}`),
      ).filter((name) => !book.has(name));
      expect(missing).toEqual([]);
    },
  );

  it.each(LANGUAGES)(
    "%s: every value's sentence has the value in it",
    (language) => {
      // A sentence that forgot {value} would show a rule with no value at all.
      const book = sentences(MESSAGES[language]);
      for (const key of RULE_KEYS)
        expect(book.get(`shopSettings.rules.${key}.shown`), key).toContain(
          "{value}",
        );
    },
  );

  it.each(LANGUAGES)("%s: every area has its name", (language) => {
    const book = sentences(MESSAGES[language]);
    const missing = AREAS.map((area) => `shopSettings.areas.${area}`).filter(
      (name) => !book.has(name),
    );
    expect(missing).toEqual([]);
    // And every rule's area is one of them.
    for (const area of Object.values(RULE_AREA)) expect(AREAS).toContain(area);
  });

  it("knows which keys it has words for", () => {
    expect(isKnownKey("attendance.late_fine")).toBe(true);
    // A key a newer server sends to an older app: the page leaves it out until the app is updated.
    expect(isKnownKey("attendance.half_day_after")).toBe(false);
    // Not a key at all, whatever an object holds by default.
    expect(isKnownKey("toString")).toBe(false);
  });
});
