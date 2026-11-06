// messages.test.ts — the two word books hold the same sentences, and every sentence can be filled in
// (UI-1, ADR-0032).
//
// A key only one book has would show its key ("home.title") on screen in the other language. A part to
// fill in that one book forgot would drop a value, like the number on "Namba ya mauzo: D2-0457".
// pnpm typecheck catches a key English lacks; these catch the rest.
import { createTranslator } from "use-intl/core";
import { describe, expect, it } from "vitest";

import { sentences } from "@/test/language";

import { LANGUAGES, MESSAGES } from "./language";

/** The names of the parts to fill in: "Namba ya mauzo: {number}" -> ["number"]. */
function blanks(sentence: string): string[] {
  return [...sentence.matchAll(/\{(\w+)\}/g)].map((match) => match[1] ?? "");
}

const swahili = sentences(MESSAGES.sw);
const english = sentences(MESSAGES.en);

describe("the word books", () => {
  it("hold the same keys", () => {
    expect([...english.keys()].sort()).toEqual([...swahili.keys()].sort());
  });

  it.each(LANGUAGES)("%s: no sentence is empty", (language) => {
    const empty = [...sentences(MESSAGES[language])].filter(
      ([, sentence]) => sentence.trim() === "",
    );
    expect(empty).toEqual([]);
  });

  it("fill in the same parts in both languages", () => {
    for (const [key, sentence] of swahili)
      expect(blanks(english.get(key) ?? "").sort(), key).toEqual(
        blanks(sentence).sort(),
      );
  });

  it.each(LANGUAGES)("%s: every sentence can be filled in", (language) => {
    // use-intl reads each sentence the first time a screen shows it. A broken one, like "Toleo
    // {version", would only fail then, on the screen that shows it: here every one is read now.
    const errors: string[] = [];
    const t = createTranslator({
      locale: language,
      messages: MESSAGES[language],
      onError: (error) => errors.push(error.message),
    });
    for (const [key, sentence] of sentences(MESSAGES[language])) {
      const values = Object.fromEntries(
        blanks(sentence).map((name) => [name, "x"]),
      );
      // The keys come from the book itself, so the type check can't know them.
      (t as (key: string, values: object) => string)(key, values);
    }
    expect(errors).toEqual([]);
  });
});
