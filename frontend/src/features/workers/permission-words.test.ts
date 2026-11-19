// permission-words.test.ts — every key (permission code) the server can send has a name in both word books and a
// group, in the server's own order (PPL-8).
//
// The codes come from shared/openapi.json, the server's own description of its API, read at run time: the list the
// worker's page offers (`permission` on give-key is a choice of them, PPL-7). `pnpm typecheck` already fails on a
// code with no group or no Swahili name (keys.ts); this test holds even if a type there is ever loosened, and it
// reads the file CI checks is up to date, so a key a later card adds can't show blank on a screen (the card's Watch
// out).
// @vitest-environment node
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { LANGUAGES, MESSAGES } from "@/i18n/language";
import { sentences } from "@/test/language";

import { EVERY_KEY, groupOf, isPermission, KEY_GROUPS } from "./keys";

/** The codes the server lists, in its order (Permission in backend/apps/core/permissions.py). */
function theServersCodes(): string[] {
  const schema = JSON.parse(
    readFileSync(resolve(process.cwd(), "../shared/openapi.json"), "utf-8"),
  ) as { components: { schemas: { PermissionEnum: { enum: string[] } } } };
  return schema.components.schemas.PermissionEnum.enum;
}

describe("the keys' words", () => {
  const codes = theServersCodes();

  it("reads the server's list", () => {
    // If the file moved or the schema renamed the list, every check below would pass on nothing.
    expect(codes).toContain("stock.count");
    expect(codes.length).toBeGreaterThan(30);
  });

  it("knows exactly the server's codes, in the server's order", () => {
    // In order: the groups and the page list keys as permissions.py does. Exactly: a code the server dropped, still
    // listed here, would be offered on the form and refused by the server.
    expect(EVERY_KEY).toEqual(codes);
  });

  it.each(LANGUAGES)("%s: every code has a name", (language) => {
    const book = sentences(MESSAGES[language]);
    const nameless = codes.filter(
      (code) => (book.get(`workers.keys.${code}`) ?? "").trim() === "",
    );
    expect(nameless).toEqual([]);
  });

  it.each(LANGUAGES)("%s: no name for a code the server lacks", (language) => {
    // A name left behind after a code was taken off the server: harmless, but the book should say what is true.
    const book = sentences(MESSAGES[language]);
    const extra = [...book.keys()]
      .filter((key) => key.startsWith("workers.keys."))
      .map((key) => key.slice("workers.keys.".length))
      .filter((code) => !codes.includes(code));
    expect(extra).toEqual([]);
  });

  it("puts every code in a group, and every group holds a code", () => {
    // groupOf for every code the server lists: a code with none would be offered under no heading.
    const used = new Set(
      codes.filter(isPermission).map((code) => groupOf(code)),
    );
    expect([...used].sort()).toEqual([...KEY_GROUPS].sort());
  });

  it("keeps each group's codes together, in the groups' order", () => {
    // The groups follow each other as permissions.py's headings do: no group comes back after another began.
    const order = EVERY_KEY.map(groupOf).filter(
      (group, index, all) => index === 0 || group !== all[index - 1],
    );
    expect(order).toEqual([...KEY_GROUPS]);
  });

  it.each(LANGUAGES)("%s: every group has a heading", (language) => {
    const book = sentences(MESSAGES[language]);
    for (const group of KEY_GROUPS)
      expect(book.get(`workers.keyGroups.${group}`), group).toBeTruthy();
  });
});
