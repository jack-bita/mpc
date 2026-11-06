// codes.test.ts — a code from the server becomes its sentence: filled in from its values, and never a
// raw key, whatever came (UI-2, ADR-0040). Which codes the books must hold: src/api/errors.test.ts.
import { createTranslator } from "use-intl/core";
import { describe, expect, it } from "vitest";

import { codeMessage, type CodeValues, type Words } from "./codes";
import { MESSAGES } from "./language";

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
