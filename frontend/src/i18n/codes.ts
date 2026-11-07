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

import { blanks } from "./blanks";

/** The values a code's sentence may need, as the server sends them in `params`. */
export type CodeValues = Record<string, string | number | boolean | null>;

/** What these functions need of use-intl's t(). The codes come from the server, so the type check can't
 * know them as keys: raw() hands over the book itself. */
export type Words = {
  (key: string, values?: CodeValues): string;
  raw(key: string): unknown;
};

/** The sentence for a code, filled in from its values. */
export function codeMessage(
  t: Words,
  code: string,
  params: CodeValues = {},
): string {
  const key = `errors.${code}`;
  const sentence = ownSentence(t, code);
  if (sentence === undefined) return t("errorFallback.unknownCode", { code });

  // A sentence asks for values by name, "dakika {minutes}". One the server didn't send can't be filled
  // in: the screen would show the key, and while building, the provider would stop the screen. So a
  // sentence missing only its wait says to wait, with no number; missing anything else, it names the code.
  const values = withMinutes(params);
  const missing = blanks(sentence).filter((name) => !(name in values));
  if (missing.length === 0) return t(key, values);
  // "Too many tries, wait a little": true for every sentence that counts minutes today, pin.locked and
  // throttled; codes.test.ts fails on a new one, which then needs a fallback of its own.
  if (missing.every((name) => name === "minutes"))
    return t("errorFallback.waitAWhile");
  return t("errorFallback.unknownCode", { code });
}

// `wait` comes in seconds (pin.locked, throttled); people read minutes. Plain numbers, not big.js: a wait
// is a count of seconds, not money or a quantity (ADR-0024).
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

// The code's sentence, walked to one part at a time through the book's `errors`: pin.locked is
// errors → pin → locked. Only the book's own entries count (Object.hasOwn): every JavaScript object also
// carries hidden names, so "constructor.name" would otherwise find "Object". A part that leads to a group,
// like errors.pin, which holds sentences but is none, isn't a sentence either.
function ownSentence(t: Words, code: string): string | undefined {
  let entry: unknown = t.raw("errors");
  for (const part of code.split(".")) {
    if (
      typeof entry !== "object" ||
      entry === null ||
      !Object.hasOwn(entry, part)
    )
      return undefined;
    entry = (entry as Record<string, unknown>)[part];
  }
  return typeof entry === "string" ? entry : undefined;
}

/** The open word book, as codeMessage() needs it. */
export function useCodeWords(): Words {
  // The one cast: use-intl's t() takes only keys it knows, and a server's code isn't one of them.
  return useTranslations() as unknown as Words;
}
