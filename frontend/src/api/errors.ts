// errors.ts — a failed call to the server, in the shop's words (UI-2, ADR-0040).
//
// The server sends no sentences for the screen, only a code and the values its sentence needs:
// `{"code": "pin.locked", "params": {"wait": 300}}`. The sentences live in the word books, under
// `errors`, nested by the code's dots: pin.locked is errors.pin.locked, "PIN zimekosewa mara nyingi...".
// errors.test.ts lists every code the API sends and checks that both books hold each one.
//
// A code with no sentence still says something useful: "Seva imekataa. Msimbo: pin.new_rule", which a
// worker can read out to the owner. That happens when a newer server meets an older app, as a device
// may run an old version for days (03 §6.5), or when a card forgets to add its code's sentences.
//
// "use client": it asks use-intl for words (use-client.test.ts says why that matters).
"use client";

import { useTranslations } from "use-intl";

import { ApiRefusal, NoConnection } from "./refusal";

type Values = Record<string, string | number | boolean | null>;

/** What these functions need of use-intl's t(). The codes come from the server, so the type check can't
 * know them as keys: has() and raw() ask the book itself. */
export type Words = {
  (key: string, values?: Values): string;
  has(key: string): boolean;
  raw(key: string): unknown;
};

/** The sentence for a failed call: a refusal, no answer at all, or anything else that was thrown. */
export function apiErrorMessage(t: Words, error: unknown): string {
  if (error instanceof ApiRefusal)
    return codeMessage(t, error.body.code, error.body.params);
  // No answer came at all: the network dropped, or the server can't be reached (client.ts). Office
  // screens also show Inahitaji mtandao while the device is offline (UI-1).
  if (error instanceof NoConnection) return t("errorFallback.noConnection");
  return t("errorFallback.unexpected");
}

/** The sentence beside each wrong field, by the field's name (`lines.1.quantity`). Only the first code of
 * each: one sentence fits under a box, and fixing it shows the next. */
export function apiFieldMessages(
  t: Words,
  error: unknown,
): Record<string, string> {
  if (!(error instanceof ApiRefusal)) return {};
  const messages: Record<string, string> = {};
  for (const [name, [code]] of Object.entries(error.body.fields))
    // A field's codes carry no values: the server fills `params` for the whole request only.
    if (code) messages[name] = codeMessage(t, code, {});
  return messages;
}

function codeMessage(t: Words, code: string, params: Values): string {
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
function withMinutes(params: Values): Values {
  const seconds = asSeconds(params.wait);
  // Rounded up, and at least 1: 30 seconds reads "dakika 1", never "dakika 0".
  return seconds === undefined
    ? params
    : { ...params, minutes: Math.max(1, Math.ceil(seconds / 60)) };
}

// The server sends a number, but the shape allows text, which a newer server might send: "300" counts
// too. Anything else, like nothing, "" (which Number() reads as 0), "soon" or a negative number, is no wait.
function asSeconds(wait: Values[string] | undefined): number | undefined {
  const seconds =
    typeof wait === "number"
      ? wait
      : typeof wait === "string" && wait.trim() !== ""
        ? Number(wait)
        : NaN;
  return Number.isFinite(seconds) && seconds >= 0 ? seconds : undefined;
}

/** The two functions above, with the open word book. */
export function useApiErrorWords() {
  // The one cast: use-intl's t() takes only keys it knows, and a server's code isn't one of them.
  const t = useTranslations() as unknown as Words;
  return {
    message: (error: unknown) => apiErrorMessage(t, error),
    fieldMessages: (error: unknown) => apiFieldMessages(t, error),
  };
}
