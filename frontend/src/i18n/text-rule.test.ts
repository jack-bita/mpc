// text-rule.test.ts — no screen can show a word typed straight into its code (UI-1, ADR-0032).
//
// The rule lives in eslint.config.mjs. Like import-rule.test.ts, these tests lint small made-up files,
// as if they sat at a given place in src/, and look for the rule's name in what ESLint reports.
//
// It runs in plain Node, as import-rule.test.ts does, because it runs ESLint.
// @vitest-environment node
import { fileURLToPath } from "node:url";

import { ESLint } from "eslint";
import { describe, expect, it } from "vitest";

const here = (name: string) => fileURLToPath(new URL(name, import.meta.url));

const RULE = "react/jsx-no-literals";

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
});
