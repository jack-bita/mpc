// codes.test.ts — a code from the server becomes its sentence: filled in from its values, and never a
// raw key, whatever came (UI-2, ADR-0040). Which codes the books must hold: src/api/errors.test.ts.
import { createTranslator } from "use-intl/core";
import { describe, expect, it } from "vitest";

import { sentences } from "@/test/language";

import { blanks } from "./blanks";
import { codeMessage, type CodeValues, type Words } from "./codes";
import { LANGUAGES, MESSAGES } from "./language";

function wordsFrom(messages: object): Words {
  // onError throws, as the provider does while building: a sentence that can't be filled in fails here.
  return createTranslator({
    locale: "sw",
    messages,
    onError: (error) => {
      throw error;
    },
  }) as unknown as Words;
}

const swahili = wordsFrom(MESSAGES.sw);

describe("codeMessage", () => {
  it("tells a PIN lock's wait in minutes, rounded up", () => {
    const locked = (wait: number) =>
      codeMessage(swahili, "pin.locked", { wait });

    expect(locked(300)).toBe(
      "PIN zimekosewa mara nyingi. Jaribu tena baada ya dakika 5.",
    );
    // Half a minute still reads as one: never "dakika 0".
    expect(locked(30)).toContain("dakika 1.");
    expect(locked(0)).toContain("dakika 1.");
    expect(locked(61)).toContain("dakika 2.");
  });

  it("reads a wait sent as text, as a newer server might send it", () => {
    expect(codeMessage(swahili, "pin.locked", { wait: "300" })).toBe(
      "PIN zimekosewa mara nyingi. Jaribu tena baada ya dakika 5.",
    );
  });

  it("never shows a key when the wait didn't come", () => {
    // Without a number the sentence can't be filled in: the screen would show "errors.pin.locked", and
    // while building, the provider would stop the screen. It says to wait, with no number.
    const noWait: CodeValues[] = [
      {},
      { wait: null },
      { wait: "" },
      { wait: "soon" },
      { wait: -5 },
    ];
    for (const params of noWait) {
      expect(codeMessage(swahili, "pin.locked", params)).toBe(
        "Majaribio mengi mno. Subiri kidogo, kisha ujaribu tena.",
      );
    }
  });

  it("tells a throttled person how long to wait, when the server says", () => {
    // DRF sends `wait` with a throttle when it knows it, in whole seconds.
    expect(codeMessage(swahili, "throttled", { wait: 45 })).toBe(
      "Majaribio mengi mno. Jaribu tena baada ya dakika 1.",
    );
    expect(codeMessage(swahili, "throttled")).toBe(
      "Majaribio mengi mno. Subiri kidogo, kisha ujaribu tena.",
    );
  });

  it("names the code when a sentence lacks any other value", () => {
    // No sentence needs another value today; a later one might, and its code must still be readable.
    const t = wordsFrom({
      errors: { sale: { below_floor: "Bei ya chini ni {floor}." } },
      errorFallback: MESSAGES.sw.errorFallback,
    });

    expect(codeMessage(t, "sale.below_floor")).toBe(
      "Seva imekataa. Msimbo: sale.below_floor",
    );
  });

  it("fills in a sentence that counts, as use-intl does", () => {
    // A plural's branches hold words, not values: "minute" is no value the server must send.
    const t = wordsFrom({
      errors: {
        pin: {
          locked:
            "Try again in {minutes} {minutes, plural, one {minute} other {minutes}}.",
        },
      },
      errorFallback: MESSAGES.sw.errorFallback,
    });

    expect(codeMessage(t, "pin.locked", { wait: 300 })).toBe(
      "Try again in 5 minutes.",
    );
  });

  it("names a code it has no sentence for, so it can be read out to the owner", () => {
    expect(codeMessage(swahili, "sale.below_floor")).toBe(
      "Seva imekataa. Msimbo: sale.below_floor",
    );
  });

  it("reads a code that names a group of sentences as one it doesn't know", () => {
    // errors.pin holds pin.wrong and the rest, but is no sentence itself.
    expect(codeMessage(swahili, "pin")).toBe("Seva imekataa. Msimbo: pin");
  });
});

// The sentence a code shows when its minutes didn't come says "too many tries, wait a little"
// (errorFallback.waitAWhile). True for every sentence that counts minutes today; a new one that isn't
// about tries must get a fallback of its own, so this list names them all.
const TRIES_WITH_MINUTES = ["errors.pin.locked", "errors.throttled"];

/** The keys of a book's code sentences that fill in `minutes`. */
function sentencesWithMinutes(book: object): string[] {
  return [...sentences(book)]
    .filter(
      ([key, sentence]) =>
        key.startsWith("errors.") && blanks(sentence).includes("minutes"),
    )
    .map(([key]) => key)
    .sort();
}

describe("the wait-a-little sentence", () => {
  it.each(LANGUAGES)(
    "%s: stands in only for sentences about tries",
    (language) => {
      expect(sentencesWithMinutes(MESSAGES[language])).toEqual(
        TRIES_WITH_MINUTES,
      );
    },
  );

  it("would catch a new sentence that counts minutes", () => {
    // The check itself, fed a book with one more: it must see it.
    const book = {
      errors: {
        ...MESSAGES.sw.errors,
        sale: { held: "Mauzo yamesimamishwa kwa dakika {minutes}." },
      },
    };

    expect(sentencesWithMinutes(book)).toContain("errors.sale.held");
  });
});
