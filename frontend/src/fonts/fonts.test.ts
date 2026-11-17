// fonts.test.ts — keeps the two fonts inside the app and out of Google's hands (UI-7, ADR-0039).
//
// A font that fails to load breaks nothing that a test would see: the browser quietly shows another
// font. So these tests check the parts that make the font work, one by one. What they can't check
// is how the letters look: that takes a real browser, and it is on the card's Done list.
//
// It runs in plain Node, as manifest.test.ts does, because it reads files on disk and runs ESLint.
// @vitest-environment node
import { createHash } from "node:crypto";
import { readFileSync, statSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { ESLint } from "eslint";
import { describe, expect, it } from "vitest";

const here = (name: string) => fileURLToPath(new URL(name, import.meta.url));

// Each font's fingerprint is here, beside its name, so that swapping one font's file for the other's
// fails too. These are the exact files whose digits were measured (src/fonts/fonts.ts).
const FONTS = [
  {
    font: "source-sans-3.woff2",
    licence: "source-sans-3-LICENSE.txt",
    sha256: "19143dca075972bc84e3fd9eab7416dd40cc565dccb2435a044bdfabe060c7d5",
    copyright:
      "Copyright 2023 Adobe (http://www.adobe.com/), with Reserved Font Name 'Source'",
  },
  {
    font: "atkinson-hyperlegible-next.woff2",
    licence: "atkinson-hyperlegible-next-LICENSE.txt",
    sha256: "18b2a1a39a2fa298b0ba5390aca68462669826c90925656f1c1f6796e0e1bbaf",
    copyright:
      "Copyright 2020-2024 The Atkinson Hyperlegible Next Project Authors (https://github.com/googlefonts/atkinson-hyperlegible-next)",
  },
];

describe.each(FONTS)("$font", ({ font, licence, sha256, copyright }) => {
  it("is the very file whose digits were measured", () => {
    // Money must line up (04 UI-7), and only a real browser can measure digits, which a unit test
    // doesn't have. So the measuring stays true only while the file stays the same. A new file is
    // allowed, but it has to come through here, and that is the moment to measure again.
    const actual = createHash("sha256")
      .update(readFileSync(here(font)))
      .digest("hex");
    expect(
      actual,
      `${font} changed: measure its digits again (fonts.ts), then update its sha256 here`,
    ).toBe(sha256);
  });

  it("is a real font file, in its small Latin version", () => {
    // Every WOFF2 file starts with these four letters. A saved error page would not, and the browser
    // would only show the next font in line, with no error anyone sees.
    expect(readFileSync(here(font)).toString("latin1", 0, 4)).toBe("wOF2");
    // The all-languages version runs to several hundred KB, on every device's offline copy (ADR-0039).
    expect(statSync(here(font)).size).toBeLessThan(40_000);
  });

  it("has its licence beside it", () => {
    // The Open Font License lets a public repo hold a font only if its licence stays with it.
    const text = readFileSync(here(licence), "utf8");
    expect(text).toContain("SIL Open Font License");
    // The licence asks that the owner's notice stays too, so the file must name this font's real
    // owner. The first line is the one from the font's own record, so the other font's licence fails.
    expect(text.split("\n")[0]).toBe(copyright);
  });
});

describe("the font switch", () => {
  // Comments removed, because only what the browser reads counts.
  const css = readFileSync(here("../app/globals.css"), "utf8").replace(
    /\/\*[\s\S]*?\*\//g,
    "",
  );

  it("hands both fonts to the page", () => {
    // Read as text, because layout.tsx imports fonts.ts, which only a Next.js build can run. Without
    // these two classes the font names don't exist on the page, and it quietly falls back to another
    // font. Both, because a person's choice changes the font with no new page (UI-9).
    const layout = readFileSync(here("../app/layout.tsx"), "utf8");
    expect(layout).toMatch(/<html[^>]*\$\{sourceSans\.variable\}/);
    expect(layout).toMatch(/<html[^>]*\$\{atkinson\.variable\}/);
  });

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

  it("sets the default font back inside a page with the second", () => {
    // /design shows both fonts side by side. Once a person's choice puts data-font="second" on <html>
    // (UI-9), its default sample would show Atkinson without this rule.
    expect(css).toMatch(
      /\[data-font="default"\]\s*\{\s*--font-body:\s*var\(--font-source-sans\)/,
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
