// format.stock.test.ts — stock reads as people count it, in each book's order: Swahili puts the word
// first, "mifuko 26 + kilo 35.5"; English the number, "26 mifuko + 35.5 kilo" (02 §15, item 1, Jack,
// 6 Nov 2026). The unit words are the shop's own, from its catalog, so they stay the same in both.
import { createTranslator } from "use-intl/core";
import { describe, expect, it } from "vitest";

import { type Language, MESSAGES } from "@/i18n/language";

import { Decimal } from "./decimal";
import { formatStock, type UnitName, type WritePart } from "./format";

/** How a screen writes a part, with the open book: t("stock.part", { count, unit }). */
function writerFor(language: Language): WritePart {
  const t = createTranslator({
    locale: language,
    messages: MESSAGES[language],
  });
  return (part) => t("stock.part", part);
}

const units = (...pairs: [string, string][]): UnitName[] =>
  pairs.map(([factor, name]) => ({ factor: new Decimal(factor), name }));

const BAGS = units(["50", "mifuko"]);

/** A stock in Swahili: by default, `quantity` kg of a product sold in bags of 50. */
const swahili = (quantity: string, sizes = BAGS, base = "kilo") =>
  formatStock(new Decimal(quantity), sizes, base, writerFor("sw"));

describe("formatStock", () => {
  it("writes E1's stock word first in Swahili, number first in English", () => {
    expect(swahili("1335.5")).toBe("mifuko 26 + kilo 35.5");
    expect(
      formatStock(new Decimal("1335.5"), BAGS, "kilo", writerFor("en")),
    ).toBe("26 mifuko + 35.5 kilo");
  });

  it("leaves out a part that is zero", () => {
    expect(swahili("1000")).toBe("mifuko 20");
    expect(swahili("35.5")).toBe("kilo 35.5");
    expect(swahili("1335.5", units(["50", "mifuko"], ["25", "nusu"]))).toBe(
      "mifuko 26 + nusu 1 + kilo 10.5",
    );
  });

  it("writes nothing at all as zero of the base unit", () => {
    expect(swahili("0")).toBe("kilo 0");
  });

  it("writes stock with no selling units in the base unit alone", () => {
    expect(swahili("1335.5", [])).toBe("kilo 1,335.5");
  });

  it("writes stock below zero with one minus before the whole", () => {
    // -120 kg counts toward zero: 2 bags and 20 kg, both below zero (ADR-0010).
    expect(swahili("-120")).toBe("-(mifuko 2 + kilo 20)");
    expect(swahili("-20")).toBe("-(kilo 20)");
  });

  it("counts bottles exactly, where floats make 0.3 L into 2 bottles", () => {
    expect(swahili("0.3", units(["0.1", "chupa"]), "lita")).toBe("chupa 3");
    expect(swahili("2.35", units(["0.1", "chupa"]), "lita")).toBe(
      "chupa 23 + lita 0.05",
    );
  });
});
