// use-client.test.ts — every file that asks use-intl for words is browser code (UI-1, ADR-0016).
//
// use-intl's hooks (useTranslations) need React's context, which only the browser's React has. A file
// without "use client" may be built as a server component: the area layouts are, and anything they
// import with no "use client" of its own is built with them. Then `next build` stops at the first page
// in an area with "createContext is not a function", far from the cause. The tests can't see it, as
// jsdom runs every file as browser code, and no page sits in an area yet. So this reads the files.
//
// It runs in plain Node, as it only reads files.
// @vitest-environment node
import { readdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

const SRC = resolve(process.cwd(), "src");

/** Every source file under src/, tests left out, by its path inside src/. */
const SOURCES = readdirSync(SRC, { recursive: true, encoding: "utf8" })
  .filter((file) => /\.(ts|tsx)$/.test(file) && !/\.test\.tsx?$/.test(file))
  .map((file) => file.split("\\").join("/"));

// An import of something that runs from "use-intl" itself. Not `import type`, which leaves nothing in
// the built code, and not "use-intl/core", which has no hooks and runs anywhere.
const USES_USE_INTL = /^import(?!\s+type\b)[^;]*from\s+"use-intl";/m;

// The directive, as the file's first statement: only comments may come before it.
const USE_CLIENT = /^(?:\s*\/\/[^\n]*\n|\s*\/\*[\s\S]*?\*\/)*\s*"use client";/;

describe('"use client"', () => {
  it("finds the files that use use-intl", () => {
    // If the pattern stopped matching, the check below would pass on nothing.
    expect(SOURCES.filter((file) => USES_USE_INTL.test(read(file)))).toEqual(
      expect.arrayContaining(["components/design/top-bar.tsx", "app/page.tsx"]),
    );
  });

  it.each(SOURCES.filter((file) => USES_USE_INTL.test(read(file))))(
    "%s says it",
    (file) => {
      expect(USE_CLIENT.test(read(file))).toBe(true);
    },
  );

  it("catches a file that forgets it", () => {
    const forgot =
      '// bar.tsx — a bar.\nimport { useTranslations } from "use-intl";\n';
    expect(USES_USE_INTL.test(forgot) && !USE_CLIENT.test(forgot)).toBe(true);
  });
});

function read(file: string): string {
  return readFileSync(resolve(SRC, file), "utf8");
}
