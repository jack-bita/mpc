// fonts.test.ts — keeps the two fonts inside the app and out of Google's hands (UI-7, ADR-0039).
//
// A font that fails to load breaks nothing that a test would see: the browser quietly shows another
// font. So these tests check the parts that make the font work, one by one. What they can't check
// is how the letters look: that takes a real browser, and it is on the card's Done list.
//
// It runs in plain Node, as manifest.test.ts does, because it reads files on disk and runs ESLint.
// @vitest-environment node
import { readFileSync, statSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { ESLint } from "eslint";
import { describe, expect, it } from "vitest";

const here = (name: string) => fileURLToPath(new URL(name, import.meta.url));

const FONTS = [
  { font: "source-sans-3.woff2", licence: "source-sans-3-LICENSE.txt" },
  {
    font: "atkinson-hyperlegible-next.woff2",
    licence: "atkinson-hyperlegible-next-LICENSE.txt",
  },
];

describe.each(FONTS)("$font", ({ font, licence }) => {
  it("is a real font file, in its small Latin version", () => {
    // Every WOFF2 file starts with these four letters. A saved error page would not, and the browser
    // would only show the next font in line, with no error anyone sees.
    expect(readFileSync(here(font)).toString("latin1", 0, 4)).toBe("wOF2");
    // The all-languages version runs to several hundred KB, on every device's offline copy (ADR-0039).
    expect(statSync(here(font)).size).toBeLessThan(40_000);
  });

  it("has its licence beside it", () => {
    // The Open Font License lets a public repo hold a font only if its licence stays with it.
    expect(readFileSync(here(licence), "utf8")).toContain(
      "SIL Open Font License",
    );
  });
});

describe("the font switch", () => {
  // Comments removed, because only what the browser reads counts.
  const css = readFileSync(here("../app/globals.css"), "utf8").replace(
    /\/\*[\s\S]*?\*\//g,
    "",
  );

  it("uses the names fonts.ts gives the two fonts", () => {
    // next/font hands each font to the page under the name in `variable`. A typo on either side would
    // show no error: the page would only fall back to a system font.
    const fonts = readFileSync(here("fonts.ts"), "utf8");
    for (const name of ["--font-source-sans", "--font-atkinson"]) {
      expect(fonts).toContain(`variable: "${name}"`);
      expect(css).toContain(`var(${name})`);
    }
  });

  it("starts on Source Sans and changes with data-font", () => {
    // By its role, not its name: a person's saved choice stays true if the font changes (ADR-0039).
    expect(css).toMatch(
      /:root\s*\{[^}]*--font-body:\s*var\(--font-source-sans\)/,
    );
    expect(css).toMatch(
      /\[data-font="second"\]\s*\{\s*--font-body:\s*var\(--font-atkinson\)/,
    );
  });

  it("reaches every Tailwind font class", () => {
    expect(css).toContain("--font-sans: var(--font-body)");
  });

  it("gives every digit the same width, on every screen", () => {
    // Atkinson's normal digits run from 407 to 648 wide, so money would not line up without this. On
    // the whole page, so no screen can forget it. Source Sans is already even and stays the same.
    expect(css).toMatch(/html\s*\{[^}]*font-variant-numeric:\s*tabular-nums/);
  });
});

describe("the lint rule", () => {
  const lint = async (code: string) => {
    const eslint = new ESLint({ cwd: here("../..") });
    const [result] = await eslint.lintText(code, {
      filePath: here("../app/example.ts"),
    });
    return result?.messages.map((message) => message.ruleId) ?? [];
  };

  // Loading ESLint and Next's rules can take a few seconds, longer than a test's normal limit.
  const SLOW = 30_000;

  it(
    "refuses fonts from Google",
    async () => {
      // next/font/google looks harmless, but it ties every build to Google's server (ADR-0039).
      const rules = await lint(
        'import { Inter } from "next/font/google";\nexport const font = Inter;\n',
      );
      expect(rules).toContain("no-restricted-imports");
    },
    SLOW,
  );

  it(
    "allows fonts from our own files",
    async () => {
      const rules = await lint(
        'import localFont from "next/font/local";\nexport const font = localFont;\n',
      );
      expect(rules).not.toContain("no-restricted-imports");
    },
    SLOW,
  );
});
