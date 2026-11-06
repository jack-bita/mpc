// codes.ts — a code from the server, in the shop's words (UI-2, ADR-0040).
//
// The server sends no sentences for the screen, only a code and the values its sentence needs:
// `{"code": "pin.locked", "params": {"wait": 300}}`. The sentences live in the word books, under
// `errors`, nested by the code's dots: pin.locked is errors.pin.locked, "PIN zimekosewa mara nyingi...".
// src/api/errors.test.ts lists every code the API sends and checks that both books hold each one.
//
// A code with no sentence still says something useful: "Seva imekataa. Msimbo: pin.new_rule", which a
// worker can read out to the owner. That happens when a newer server meets an older app, as a device
// may run an old version for days (03 §6.5), or when a card forgets to add its code's sentences.
//
// Here, beside the word books, not in src/api/: office screens read codes from the API's refusals
// (src/api/errors.ts), and counter screens will read them from sync's, while the counter lock keeps
// them out of src/api/ (rule 5, eslint.config.mjs).
//
// "use client": it asks use-intl for words (use-client.test.ts says why that matters).
"use client";

import { useTranslations } from "use-intl";

/** The values a code's sentence may need, as the server sends them in `params`. */
export type CodeValues = Record<string, string | number | boolean | null>;

/** What these functions need of use-intl's t(). The codes come from the server, so the type check can't
 * know them as keys: has() and raw() ask the book itself. */
export type Words = {
  (key: string, values?: CodeValues): string;
  has(key: string): boolean;
  raw(key: string): unknown;
};

/** The sentence for a code, filled in from its values. */
export function codeMessage(
  t: Words,
  code: string,
  params: CodeValues = {},
): string {
  const key = `errors.${code}`;
  // has() is also true for a group, like errors.pin, which holds sentences but is none: raw() tells.
  const sentence = t.has(key) ? t.raw(key) : undefined;
  if (typeof sentence !== "string")
    return t("errorFallback.unknownCode", { code });

  // A sentence asks for values by name, "dakika {minutes}". One the server didn't send can't be filled
  // in: the screen would show the key, and while building, the provider would stop the screen. So a
  // sentence missing only its wait says to wait, with no number; missing anything else, it names the code.
  const values = withMinutes(params);
  const missing = blanks(sentence).filter((name) => !(name in values));
  if (missing.length === 0) return t(key, values);
  if (missing.every((name) => name === "minutes"))
    return t("errorFallback.waitAWhile");
  return t("errorFallback.unknownCode", { code });
}

// The names a sentence fills in: "{minutes}", and "{count, plural, ...}" should a sentence ever count.
function blanks(sentence: string): string[] {
  return [...sentence.matchAll(/\{(\w+)[},]/g)].map((match) => match[1] ?? "");
}

// `wait` comes in seconds (pin.locked); people read minutes. Plain numbers, not big.js: a wait is a count
// of seconds, not money or a quantity (ADR-0024).
function withMinutes(params: CodeValues): CodeValues {
  const seconds = asSeconds(params.wait);
  // Rounded up, and at least 1: 30 seconds reads "dakika 1", never "dakika 0".
  return seconds === undefined
    ? params
    : { ...params, minutes: Math.max(1, Math.ceil(seconds / 60)) };
}

// The server sends a number, but the shape allows text, which a newer server might send: "300" counts
// too. Anything else, like nothing, "" (which Number() reads as 0), "soon" or a negative number, is no wait.
function asSeconds(wait: CodeValues[string] | undefined): number | undefined {
  const seconds =
    typeof wait === "number"
      ? wait
      : typeof wait === "string" && wait.trim() !== ""
        ? Number(wait)
        : NaN;
  return Number.isFinite(seconds) && seconds >= 0 ? seconds : undefined;
}

/** The open word book, as codeMessage() needs it. */
export function useCodeWords(): Words {
  // The one cast: use-intl's t() takes only keys it knows, and a server's code isn't one of them.
  return useTranslations() as unknown as Words;
}
