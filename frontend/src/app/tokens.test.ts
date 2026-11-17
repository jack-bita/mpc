// tokens.test.ts — keeps the shop's look true by numbers, not by eye (UI-7, ADR-0039).
//
// A wrong colour breaks no code, so nothing else would notice it: a pale text colour would pass the
// type checks and the page tests, and only hurt at the counter, with daylight on a cheap screen.
//
// It reads globals.css as plain text, because jsdom applies no stylesheet and lays out nothing. So it
// runs in plain Node, as manifest.test.ts does, and can only check what the file says.
//
// The file and the sums come from src/test/look.ts, which the pieces' tests share, so the tokens and the
// pieces are judged by one formula (UI-8).
// @vitest-environment node
import { describe, expect, it } from "vitest";

import { colour, contrast, CSS, TOKENS } from "@/test/look";

// Each pair that a screen really shows: [the text, what is behind it].
const TEXT_PAIRS = [
  // Normal and quiet text, on a white screen and on a pale panel.
  ["--foreground", "--background"],
  ["--foreground", "--muted"],
  ["--muted-foreground", "--background"],
  ["--muted-foreground", "--muted"],
  // What sits on the panels shadcn's parts draw.
  ["--card-foreground", "--card"],
  // A card's footer: the card's text on the pale panel (components/design/card.tsx). The same colour as
  // --foreground today, which is why it passed unchecked; a change to one alone must still be caught.
  ["--card-foreground", "--muted"],
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

describe("the shop's shapes", () => {
  it("keeps the card's corners and control heights", () => {
    // Pinned here because no sum can judge them, and they set how every button feels under a finger.
    expect(TOKENS.get("--radius")).toBe("8px");
    expect(TOKENS.get("--control-big")).toBe("52px");
    expect(TOKENS.get("--control-normal")).toBe("44px");
  });
});

describe("what shadcn left behind", () => {
  it("leaves no placeholder colour", () => {
    // Every grey that `shadcn init` wrote is an oklch() value; the shop's colours are plain hex.
    expect(CSS).not.toContain("oklch(");
  });

  it("leaves no chart or sidebar tokens, whatever their colour", () => {
    // `shadcn add` can write these back. No screen uses them, and a card that needs them gives them the
    // shop's colours. Written in hex they would pass the oklch check above.
    expect(CSS).not.toMatch(/--(color-)?(chart|sidebar)/);
  });

  it("writes every colour in hex", () => {
    // Only the tokens in the pairs above get their contrast checked. This also covers --border, which
    // no pair names, so a grey in another notation can't hide there.
    const notColours = [
      "--radius",
      "--control-big",
      "--control-normal",
      "--font-body",
    ];
    for (const name of TOKENS.keys())
      if (!notColours.includes(name)) colour(name);
  });

  it("keeps one list of tokens", () => {
    // The checks read the first :root. A second one further down would win in the browser, and could
    // bring back any colour these checks refuse.
    expect(CSS.match(/:root\s*\{/g)).toHaveLength(1);
  });

  it("removes the dark colours", () => {
    // Light only for now (ADR-0039). Half-finished dark colours would still be applied by any
    // class="dark", so none is kept.
    expect(CSS).not.toMatch(/^\.dark\s*\{/m);
  });

  it("asks browsers not to darken the page", () => {
    // Chrome's Auto Dark Theme can darken a light page by itself. Light only means our colours are the
    // ones on screen, and the contrast sums above only hold for those (ADR-0039).
    expect(CSS).toMatch(/:root\s*\{[^}]*color-scheme:\s*only light/);
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
