// errors.ts — a failed call to the server, in the shop's words (UI-2, ADR-0040).
//
// A failed call is one of three things: the server refused it (ApiRefusal, with a code), no answer came
// at all (NoConnection), or something else was thrown, a bug. A refusal's code becomes its sentence in
// src/i18n/codes.ts, which counter screens can use too; this file says what to show for each failure.
//
// "use client": its hook asks use-intl for words, through useCodeWords() (use-client.test.ts).
"use client";

import { codeMessage, useCodeWords, type Words } from "@/i18n/codes";

import { ApiRefusal, NoConnection } from "./refusal";

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
    if (code) messages[name] = codeMessage(t, code);
  return messages;
}

/** The two functions above, with the open word book. */
export function useApiErrorWords() {
  const t = useCodeWords();
  return {
    message: (error: unknown) => apiErrorMessage(t, error),
    fieldMessages: (error: unknown) => apiFieldMessages(t, error),
  };
}
