// tokens.test.ts — keeps the shop's look true by numbers, not by eye (UI-7, ADR-0039).
//
// A wrong colour breaks no code, so nothing else would notice it: a pale text colour would pass the
// type checks and the page tests, and only hurt at the counter, with daylight on a cheap screen.
//
// It reads globals.css as plain text, because jsdom applies no stylesheet and lays out nothing. So it
// runs in plain Node, as manifest.test.ts does, and can only check what the file says.
// @vitest-environment node
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

// The file with its comments removed: they may name old values on purpose, like the first faded red,
// and only what the browser reads counts.
const CSS = readFileSync(
  fileURLToPath(new URL("./globals.css", import.meta.url)),
  "utf8",
).replace(/\/\*[\s\S]*?\*\//g, "");

/** The value of every token in the first `:root` block, by name: "--primary" -> "#15803d". */
function readTokens(css: string): Map<string, string> {
  const block = /:root\s*\{([^}]*)\}/.exec(css)?.[1];
  if (block === undefined) throw new Error("globals.css has no :root block");
  return new Map(
    [...block.matchAll(/(--[\w-]+):\s*([^;]+);/g)].map(
      (match): [string, string] => [match[1] ?? "", (match[2] ?? "").trim()],
    ),
  );
}

const TOKENS = readTokens(CSS);

/** How bright a colour looks to the eye, from 0 (black) to 1 (white): the WCAG formula. */
function brightness(hex: string): number {
  // Screens store colours bent to suit the eye; the formula needs them straightened out first.
  const channel = (start: number) => {
    const value = Number.parseInt(hex.slice(start, start + 2), 16) / 255;
    return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
  };
  // Weighted because the eye is most sensitive to green and least to blue.
  return 0.2126 * channel(1) + 0.7152 * channel(3) + 0.0722 * channel(5);
}

/** The contrast of two colours: 1 for the same colour, 21 for black on white. The order doesn't matter. */
function contrast(first: string, second: string): number {
  const lighter = Math.max(brightness(first), brightness(second));
  const darker = Math.min(brightness(first), brightness(second));
  return (lighter + 0.05) / (darker + 0.05);
}

/**
 * A token's colour; a token that isn't plain hex fails here, so the sums never run on a bad value.
 * Small letters only, because Prettier rewrites a CSS colour that way when it formats the file.
 */
function colour(name: string): string {
  const value = TOKENS.get(name);
  expect(value, `${name} should be a colour like #15803d`).toMatch(
    /^#[0-9a-f]{6}$/,
  );
  return value as string;
}

// Each pair that a screen really shows: [the text, what is behind it].
const TEXT_PAIRS = [
  // Normal and quiet text, on a white screen and on a pale panel.
  ["--foreground", "--background"],
  ["--foreground", "--muted"],
  ["--muted-foreground", "--background"],
  ["--muted-foreground", "--muted"],
  // What sits on the panels shadcn's parts draw.
  ["--card-foreground", "--card"],
  ["--popover-foreground", "--popover"],
  ["--accent-foreground", "--accent"],
  // Text on a filled button.
  ["--primary-foreground", "--primary"],
  ["--secondary-foreground", "--secondary"],
  // The colours used as text themselves: green and blue links, faded-red warnings.
  ["--primary", "--background"],
  ["--primary", "--muted"],
  ["--secondary", "--background"],
  ["--secondary", "--muted"],
  ["--destructive", "--background"],
  ["--destructive", "--muted"],
  // White on a filled warning: shadcn has no token for this text, so the button's white stands in.
  ["--primary-foreground", "--destructive"],
] as const;

// What must be seen, though it isn't text. WCAG asks 3:1 for these. --border isn't here on purpose:
// a pale line only decorates, and nothing depends on seeing it.
const EDGE_PAIRS = [
  // A white box on a white screen: this edge is all that shows where to type (Jack, 5 Nov 2026).
  ["--input", "--background"],
  ["--input", "--muted"],
  // The focus ring is how someone on a keyboard knows where they are.
  ["--ring", "--background"],
  ["--ring", "--muted"],
] as const;

describe("the shop's colours", () => {
  it.each(TEXT_PAIRS)("%s reads on %s at 4.5:1 or better", (text, behind) => {
    expect(contrast(colour(text), colour(behind))).toBeGreaterThanOrEqual(4.5);
  });

  it.each(EDGE_PAIRS)("%s shows on %s at 3:1 or better", (edge, behind) => {
    expect(contrast(colour(edge), colour(behind))).toBeGreaterThanOrEqual(3);
  });
});

describe("page-wide defaults", () => {
  it("shows the hand pointer on a button", () => {
    // Tailwind 4 gives buttons the plain arrow. jsdom has no mouse, so this only checks the rule is
    // there; that it works is on the card's Done list, checked in a real browser.
    expect(CSS).toMatch(/button:not\(:disabled\)[^{]*\{\s*cursor:\s*pointer/);
  });
});

describe("what shadcn left behind", () => {
  it("leaves no placeholder colour", () => {
    // Every grey that `shadcn init` wrote is an oklch() value; the shop's colours are plain hex.
    expect(CSS).not.toContain("oklch(");
  });

  it("removes the dark colours", () => {
    // Light only for now (ADR-0039). Half-finished dark colours would still be applied by any
    // class="dark", so none is kept.
    expect(CSS).not.toMatch(/^\.dark\s*\{/m);
  });

  it("keeps the dark: classes switched off", () => {
    // shadcn's parts carry dark: classes. Without this line those classes follow the device's setting,
    // and a phone in dark mode gets half-dark screens. With it, they wait for a class no page has.
    expect(CSS).toContain("@custom-variant dark (&:is(.dark *));");
  });

  it("keeps the focus ring at full strength", () => {
    // shadcn's default fades the ring to half strength, 2.57:1 on white: under the 3:1 checked above,
    // which only sees the token and not this class.
    expect(CSS).toContain("outline-ring;");
    expect(CSS).not.toContain("outline-ring/");
  });

  it("gives every name Tailwind uses a value", () => {
    // @theme maps each token to the class names (--color-primary makes bg-primary). A name left there
    // with no value would still make a class, and that class would quietly paint nothing.
    const theme = /@theme inline\s*\{([^}]*)\}/.exec(CSS)?.[1];
    if (theme === undefined) throw new Error("globals.css has no @theme block");
    const used = [...theme.matchAll(/var\((--[\w-]+)\)/g)].map(
      (match) => match[1] ?? "",
    );
    expect(used.length).toBeGreaterThan(0);
    for (const name of used) expect(TOKENS.has(name), name).toBe(true);
  });
});
