// text-rule.test.ts — no screen can show a word typed straight into its code, between tags or in an
// attribute a person reads or hears, like placeholder or aria-label (UI-1, ADR-0040).
//
// The two rules live in eslint.config.mjs. Like import-rule.test.ts, these tests lint small made-up files,
// as if they sat at a given place in src/, and look for the rule's name in what ESLint reports.
//
// It runs in plain Node, as import-rule.test.ts does, because it runs ESLint.
// @vitest-environment node
import { fileURLToPath } from "node:url";

import { ESLint } from "eslint";
import { describe, expect, it } from "vitest";

const here = (name: string) => fileURLToPath(new URL(name, import.meta.url));

const RULE = "react/jsx-no-literals";
// The rule that refuses a word typed into an attribute that holds words (eslint.config.mjs).
const ATTRIBUTE_RULE = "no-restricted-syntax";

/** The rules ESLint names for `code`, as if it were the file at `place` (from src/i18n/). */
async function rulesFor(
  place: string,
  code: string,
): Promise<(string | null)[]> {
  const eslint = new ESLint({ cwd: here("../..") });
  const [result] = await eslint.lintText(code, { filePath: here(place) });
  return result?.messages.map((message) => message.ruleId) ?? [];
}

// Loading ESLint and Next's rules can take a few seconds, longer than a test's normal limit.
const SLOW = 30_000;

/** A made-up screen that shows `shown` inside a <p>. */
const screenShowing = (shown: string) =>
  `const t = (key: string) => key;\nconst version = "dev";\nexport function Screen() {\n  return <p className="text-sm">${shown}</p>;\n}\n`;

/** A made-up screen with one <input> that carries `attribute`. */
const inputWith = (attribute: string) =>
  `const t = (key: string) => key;\nconst version = "dev";\nexport function Screen() {\n  return <input className="w-full" ${attribute} />;\n}\n`;

describe("the text rule", () => {
  it.each([
    ["between tags", "Karibu"],
    ["as code", '{"Karibu"}'],
    ["as a template", "{`Toleo ${version}`}"],
  ])(
    "refuses a word typed %s",
    async (_, shown) => {
      expect(
        await rulesFor("../app/sale/page.tsx", screenShowing(shown)),
      ).toContain(RULE);
    },
    SLOW,
  );

  it(
    "lets a screen show words from the books, with class names on it",
    async () => {
      expect(
        await rulesFor(
          "../app/sale/page.tsx",
          screenShowing('{t("home.title")}'),
        ),
      ).not.toContain(RULE);
    },
    SLOW,
  );

  it(
    "refuses one in a piece of the look too",
    async () => {
      expect(
        await rulesFor(
          "../components/design/top-bar.tsx",
          screenShowing("MPC"),
        ),
      ).toContain(RULE);
    },
    SLOW,
  );

  it(
    "lets a test write the words it expects to see",
    async () => {
      expect(
        await rulesFor("../app/sale/page.test.tsx", screenShowing("Karibu")),
      ).not.toContain(RULE);
    },
    SLOW,
  );

  it.each([
    ["placeholder", 'placeholder="Tafuta"'],
    ["aria-label, as code", 'aria-label={"Funga"}'],
    ["title, as a template", "title={`Toleo ${version}`}"],
    ["alt", 'alt="Nembo"'],
    ["aria-description", 'aria-description="Bei ya jumla"'],
  ])(
    "refuses a word typed into %s",
    async (_, attribute) => {
      expect(
        await rulesFor("../app/sale/page.tsx", inputWith(attribute)),
      ).toContain(ATTRIBUTE_RULE);
    },
    SLOW,
  );

  it.each([
    ["a word from the books", 'placeholder={t("design.fields.search")}'],
    ["an empty alt, on a picture that only decorates", 'alt=""'],
    ["an attribute that holds no words", 'type="search"'],
  ])(
    "lets an attribute hold %s",
    async (_, attribute) => {
      expect(
        await rulesFor("../app/sale/page.tsx", inputWith(attribute)),
      ).not.toContain(ATTRIBUTE_RULE);
    },
    SLOW,
  );
});
