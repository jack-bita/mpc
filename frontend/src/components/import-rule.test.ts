// import-rule.test.ts — no screen can skip the shop's look by importing shadcn's raw parts (UI-8, ADR-0039),
// and no counter screen can call the server (UI-2, rule 5, ADR-0019).
//
// The rules live in eslint.config.mjs. These tests lint small made-up files, as if they sat at a given
// place in src/, and look for the rule's name in what ESLint reports. The imports point at real files
// (components/ui/button.tsx, components/design/button.tsx), as the rule follows each import to its file.
//
// It runs in plain Node, as fonts.test.ts does, because it runs ESLint.
// @vitest-environment node
import { fileURLToPath } from "node:url";

import { ESLint } from "eslint";
import { describe, expect, it } from "vitest";

const here = (name: string) => fileURLToPath(new URL(name, import.meta.url));

const RULE = "import/no-restricted-paths";

/** The rules ESLint names for `code`, as if it were the file at `place` (from src/components/). */
async function rulesFor(
  place: string,
  code: string,
): Promise<(string | null)[]> {
  const eslint = new ESLint({ cwd: here("../..") });
  const [result] = await eslint.lintText(code, { filePath: here(place) });
  return result?.messages.map((message) => message.ruleId) ?? [];
}

// Loading ESLint, Next's rules and the path resolver can take a few seconds, longer than a test's normal limit.
const SLOW = 30_000;

const RAW_BUTTON =
  'import { Button } from "@/components/ui/button";\nexport const Piece = Button;\n';
const OUR_BUTTON =
  'import { Button } from "@/components/design/button";\nexport const Piece = Button;\n';

describe("the import rule", () => {
  it(
    "refuses shadcn's parts on a screen",
    async () => {
      expect(await rulesFor("../app/sale/page.tsx", RAW_BUTTON)).toContain(
        RULE,
      );
    },
    SLOW,
  );

  it.each(["page.jsx", "page.js", "page.mjs", "page.mts", "page.cts"])(
    "refuses them in a screen written as %s",
    async (file) => {
      // tsconfig.json allows JavaScript, and Next.js routes a page.jsx as readily as a page.tsx. Not
      // .cjs: Next's rule sets don't lint it, and a CommonJS file can't be a page (eslint.config.mjs).
      expect(await rulesFor(`../app/sale/${file}`, RAW_BUTTON)).toContain(RULE);
    },
    SLOW,
  );

  it(
    "refuses them by any path, not only by the @/ name",
    async () => {
      const relative =
        'import { Button } from "../../components/ui/button";\nexport const Piece = Button;\n';
      expect(await rulesFor("../app/sale/page.tsx", relative)).toContain(RULE);
    },
    SLOW,
  );

  it(
    "refuses them in a component that isn't one of our pieces",
    async () => {
      // Like update-prompt.tsx, beside design/: a shared part of a screen is still a screen here.
      expect(await rulesFor("./top-bar.tsx", RAW_BUTTON)).toContain(RULE);
    },
    SLOW,
  );

  it(
    "lets a screen use our pieces",
    async () => {
      expect(await rulesFor("../app/sale/page.tsx", OUR_BUTTON)).not.toContain(
        RULE,
      );
    },
    SLOW,
  );

  it(
    "lets our pieces wrap shadcn's parts",
    async () => {
      expect(
        await rulesFor("./design/new-piece.tsx", RAW_BUTTON),
      ).not.toContain(RULE);
    },
    SLOW,
  );

  it(
    "still refuses fonts from Google in our pieces",
    async () => {
      // A rule given twice in ESLint's settings keeps only the last options for a file. This one is
      // a different rule, so the font ban (UI-7) must still reach the folder the import rule leaves out.
      const google =
        'import { Inter } from "next/font/google";\nexport const font = Inter;\n';
      expect(await rulesFor("./design/new-piece.tsx", google)).toContain(
        "no-restricted-imports",
      );
    },
    SLOW,
  );
});

describe("the counter rule", () => {
  // A counter screen sits in app/(counter)/. The brackets are Next's way to group routes without a part in
  // the address; some path tools read brackets as a pattern, so these tests also prove the rules reach it.
  const COUNTER = "../app/(counter)/sale/page.tsx";
  const OFFICE = "../app/(office)/devices/page.tsx";
  const API =
    'import { api } from "@/api/client";\nexport const client = api;\n';
  const QUERY =
    'import { useQuery } from "@tanstack/react-query";\nexport const ask = useQuery;\n';

  it(
    "refuses the API client on a counter screen",
    async () => {
      expect(await rulesFor(COUNTER, API)).toContain(RULE);
    },
    SLOW,
  );

  it(
    "refuses it by any path, not only by the @/ name",
    async () => {
      const relative =
        'import { api } from "../../../api/client";\nexport const client = api;\n';
      expect(await rulesFor(COUNTER, relative)).toContain(RULE);
    },
    SLOW,
  );

  it(
    "refuses TanStack Query on a counter screen",
    async () => {
      expect(await rulesFor(COUNTER, QUERY)).toContain("no-restricted-imports");
    },
    SLOW,
  );

  it(
    "still refuses fonts from Google on a counter screen",
    async () => {
      // The counter's rule is no-restricted-imports, like the font ban, and ESLint keeps only the last
      // settings of a rule for a file: the ban must be listed again there (eslint.config.mjs).
      const google =
        'import { Inter } from "next/font/google";\nexport const font = Inter;\n';
      expect(await rulesFor(COUNTER, google)).toContain(
        "no-restricted-imports",
      );
    },
    SLOW,
  );

  it(
    "lets an office screen use both",
    async () => {
      const rules = await rulesFor(OFFICE, API + QUERY);
      expect(rules).not.toContain(RULE);
      expect(rules).not.toContain("no-restricted-imports");
    },
    SLOW,
  );
});
