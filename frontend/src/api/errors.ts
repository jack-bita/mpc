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

import { ApiRefusal } from "./refusal";

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
  // fetch throws a TypeError when no answer came at all: the network dropped, or the server can't be
  // reached. Office screens also show Inahitaji mtandao while the device is offline (UI-1).
  if (error instanceof TypeError) return t("errorFallback.noConnection");
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
  if (!t.has(key) || typeof t.raw(key) !== "string")
    return t("errorFallback.unknownCode", { code });
  return t(key, withMinutes(params));
}

// `wait` comes in seconds (pin.locked); people read minutes. Rounded up, so 30 seconds reads "1", never
// "0". Plain numbers, not big.js: a wait is a count of seconds, not money or a quantity (ADR-0024).
function withMinutes(params: Values): Values {
  const { wait } = params;
  return typeof wait === "number"
    ? { ...params, minutes: Math.ceil(wait / 60) }
    : params;
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
