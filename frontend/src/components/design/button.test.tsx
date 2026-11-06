// button.test.tsx — the shop's button keeps its colours readable and its behaviour safe (UI-8, ADR-0039).
//
// jsdom paints nothing, so the colour checks read the classes the browser really gets, after shadcn's
// own classes and ours are merged, and do the sums on them with the tokens from globals.css. A class
// that slips through the merge, like shadcn's faded hover (bg-primary/80), is caught here. Seeing the
// colours, the hover and the ring is on the card's Done list, on /design.
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { colour, contrast, mix, TOKENS } from "@/test/look";

import { Button, BUTTON_KINDS, BUTTON_SIZES } from "./button";

// What a button can sit on: a white screen and a pale panel.
const BEHIND = [
  ["white", colour("--background")],
  ["pale panel", colour("--muted")],
] as const;

/** The classes of one button, as the browser gets them. */
function classesOf(props: Parameters<typeof Button>[0] = {}): string[] {
  render(<Button {...props}>Hifadhi</Button>);
  return screen.getByRole("button", { name: "Hifadhi" }).className.split(/\s+/);
}

/** What a background class paints over `behind`. Fails on a form the sums don't know. */
function paint(value: string, behind: string): string {
  // bg-[color-mix(in_srgb,var(--primary)_88%,black)]: the colour darkened, solid.
  const darkened =
    /^\[color-mix\(in_srgb,var\((--[\w-]+)\)_(\d+)%,black\)\]$/.exec(value);
  if (darkened)
    return mix(colour(darkened[1] ?? ""), "#000000", Number(darkened[2]) / 100);
  // bg-destructive/5: a see-through tint, over whatever is behind the button.
  const tint = /^([\w-]+)\/(\d+)$/.exec(value);
  if (tint) return mix(colour(`--${tint[1]}`), behind, Number(tint[2]) / 100);
  // bg-primary: a token, solid. colour() fails on anything else, so a new form must be added here.
  return colour(`--${value}`);
}

/** A text colour class's colour. Faded text (text-primary-foreground/80) fails: no sum covers it. */
function ink(value: string): string {
  expect(value, "text at full strength, not faded").not.toContain("/");
  // A token, or it fails: a palette colour like text-red-500 isn't one of the shop's.
  return colour(`--${value}`);
}

/**
 * A class split into its states and its utility: "hover:bg-primary" is "hover:" and "bg-primary". A
 * colon inside [...] or (...) belongs to its part, as in [&_svg:not(...)]:size-5.
 */
function split(name: string): { state: string; utility: string } {
  let depth = 0;
  let cut = 0;
  [...name].forEach((letter, at) => {
    if (letter === "[" || letter === "(") depth += 1;
    else if (letter === "]" || letter === ")") depth -= 1;
    else if (letter === ":" && depth === 0) cut = at + 1;
  });
  return { state: name.slice(0, cut), utility: name.slice(cut) };
}

// text- classes that set a size, an alignment or wrapping, not a colour.
const TEXT_NOT_COLOUR =
  /^text-(xs|sm|base|lg|\d?xl|left|center|right|justify|start|end|wrap|nowrap|balance|pretty|ellipsis|clip)$/;

/**
 * Every state the button has a colour for, whatever its name ("" at rest, "hover:", "active:",
 * "aria-expanded:", or one a later `shadcn add` brings), with its backgrounds and text colours. Left
 * out: dark:, which never applies (UI-7), and the switched-off states, as WCAG asks no contrast of a
 * control that can't be used, and ours fade on purpose.
 */
function colourStates(classes: string[]) {
  const states = new Map<string, { bg: string[]; text: string[] }>();
  for (const name of classes) {
    const { state, utility } = split(name);
    if (state.includes("dark:") || state.includes("disabled")) continue;
    const entry = states.get(state) ?? { bg: [], text: [] };
    // bg-clip-padding is about where the paint stops, not its colour.
    if (utility.startsWith("bg-") && !utility.startsWith("bg-clip-"))
      entry.bg.push(utility.slice("bg-".length));
    else if (utility.startsWith("text-") && !TEXT_NOT_COLOUR.test(utility))
      entry.text.push(utility.slice("text-".length));
    else continue;
    states.set(state, entry);
  }
  return states;
}

/** Every state's text reads at 4.5:1 on what it is painted on, on white and on a pale panel. */
function expectReadable(classes: string[]) {
  const states = colourStates(classes);
  const rest = states.get("");
  expect(rest?.text, "a colour for the text at rest").toHaveLength(1);
  for (const [state, own] of states) {
    // A state with no colour of its own keeps the colour it has at rest.
    const texts = own.text.length ? own.text : (rest?.text ?? []);
    const backgrounds = own.bg.length ? own.bg : (rest?.bg ?? []);
    for (const text of texts)
      for (const [where, behind] of BEHIND)
        // No background at all: the button is see-through, and the screen shows.
        for (const background of backgrounds.length ? backgrounds : [null]) {
          const painted =
            background === null ? behind : paint(background, behind);
          expect(
            contrast(ink(text), painted),
            `${state || "at rest"} on ${where}`,
          ).toBeGreaterThanOrEqual(4.5);
        }
  }
}

/** Nothing fades the whole button but switching it off: opacity takes the text down with it. */
function expectNoFade(classes: string[]) {
  const fades = classes.filter((name) => {
    const { state, utility } = split(name);
    return utility.startsWith("opacity-") && !state.includes("disabled");
  });
  expect(fades).toEqual([]);
}

// The text colour each kind keeps in every state: an outline that turned dark on hover, as shadcn's
// does, would still read well enough, and stop looking like itself.
const OWN_TEXT = {
  main: "primary-foreground",
  second: "secondary",
  danger: "destructive",
} as const;

function expectOwnText(kind: (typeof BUTTON_KINDS)[number], classes: string[]) {
  const texts = [...colourStates(classes).values()].flatMap(
    (state) => state.text,
  );
  expect(texts.length).toBeGreaterThan(0);
  for (const text of texts) expect(text).toBe(OWN_TEXT[kind]);
}

/** Every background in every state. */
function backgroundsOf(classes: string[]): string[] {
  return [...colourStates(classes).values()].flatMap((state) => state.bg);
}

describe("the button's colours", () => {
  it.each(BUTTON_KINDS)(
    "%s: the text reads at 4.5:1 in every state, on white and on a pale panel",
    (kind) => {
      expectReadable(classesOf({ kind }));
    },
  );

  it.each(BUTTON_KINDS)("%s: nothing fades it but switching it off", (kind) => {
    expectNoFade(classesOf({ kind }));
  });

  it.each(BUTTON_KINDS)("%s: the text keeps its own colour", (kind) => {
    expectOwnText(kind, classesOf({ kind }));
  });

  it("main darkens and never fades", () => {
    // White on green faded to 90% reads at only 4.17:1 (UI-7). A fade is the bg-primary/N form.
    const classes = classesOf({ kind: "main" });
    expect(
      backgroundsOf(classes).filter((value) => value.includes("/")),
    ).toEqual([]);
    expect(classes).toContain(
      "hover:bg-[color-mix(in_srgb,var(--primary)_88%,black)]",
    );
  });

  it.each(["second", "danger"] as const)(
    "%s: a light tint, 5 in 100 at most",
    (kind) => {
      // The danger limit is the card's: --destructive on its own 10% tint, over a pale panel, reads at
      // only 4.21:1. The blue has room to spare, and keeps the same limit so the two outlines match.
      const tints = backgroundsOf(classesOf({ kind }))
        .map((value) => /\/(\d+)$/.exec(value)?.[1])
        .filter((share) => share !== undefined);
      expect(tints.length).toBeGreaterThan(0);
      for (const share of tints) expect(Number(share)).toBeLessThanOrEqual(5);
    },
  );

  it.each(BUTTON_KINDS)("%s: the focus ring is at full strength", (kind) => {
    // shadcn's ring-ring/50 reads at only 2.57:1 on white; its danger ring is a faint red.
    const classes = classesOf({ kind });
    expect(classes).toContain("focus-visible:ring-ring");
    expect(
      classes.filter((name) => /^focus-visible:ring-.*\//.test(name)),
    ).toEqual([]);
    expect(
      classes.filter((name) =>
        name.startsWith("focus-visible:ring-destructive"),
      ),
    ).toEqual([]);
  });
});

describe("the colour checks themselves", () => {
  // Each check fed one class that breaks its rule must fail, or it could pass by accident.
  it("catch faded text on hover", () => {
    const classes = classesOf({
      kind: "main",
      className: "hover:text-primary-foreground/80",
    });
    expect(() => expectReadable(classes)).toThrow();
  });

  it("catch a state they have no name for", () => {
    // A state a later shadcn add could bring, painted grey with dark text.
    const classes = classesOf({
      kind: "main",
      className: "data-popup-open:bg-muted",
    });
    expect(() => expectReadable(classes)).toThrow();
  });

  it("catch a button faded by opacity", () => {
    const classes = classesOf({ kind: "main", className: "hover:opacity-90" });
    expect(() => expectNoFade(classes)).toThrow();
  });

  it("catch an outline whose text turns dark on hover", () => {
    // shadcn's own outline does this (hover:text-foreground).
    const classes = classesOf({
      kind: "second",
      className: "hover:text-foreground",
    });
    expect(() => expectOwnText("second", classes)).toThrow();
  });
});

describe("the button's shape", () => {
  it.each([
    ["big", "h-(--control-big)", "--control-big", "52px"],
    ["normal", "h-(--control-normal)", "--control-normal", "44px"],
  ] as const)("%s: one height, %s", (size, height, token, pixels) => {
    // Two height classes would leave the choice to CSS order; shadcn's h-8 must be gone.
    const classes = classesOf({ size });
    expect(classes.filter((name) => /^(h|size)-/.test(name))).toEqual([height]);
    expect(TOKENS.get(token)).toBe(pixels);
  });

  it("is main and big unless told otherwise", () => {
    const classes = classesOf();
    expect(classes).toContain("bg-primary");
    expect(classes).toContain("h-(--control-big)");
  });

  it("has the kinds and sizes the card names", () => {
    // Screens and /design use these names; a rename must change the card too.
    expect(BUTTON_SIZES).toEqual(["big", "normal"]);
    expect(BUTTON_KINDS).toEqual(["main", "second", "danger"]);
  });

  it("keeps a screen's own classes", () => {
    expect(classesOf({ className: "w-full" })).toContain("w-full");
  });
});

describe("the button's behaviour", () => {
  it("is a real button that never sends a form by accident", () => {
    // type="button" from Base UI: a <button> in a form would otherwise send the form when pressed.
    render(<Button>Hifadhi</Button>);
    const button = screen.getByRole("button", { name: "Hifadhi" });
    expect(button.tagName).toBe("BUTTON");
    expect(button.getAttribute("type")).toBe("button");
  });

  it("sends a form when it says so", () => {
    render(<Button type="submit">Hifadhi</Button>);
    expect(screen.getByRole("button").getAttribute("type")).toBe("submit");
  });

  it("does nothing when switched off", () => {
    const pressed = vi.fn();
    render(
      <Button disabled onClick={pressed}>
        Hifadhi
      </Button>,
    );
    const button = screen.getByRole("button", { name: "Hifadhi" });
    fireEvent.click(button);
    expect(pressed).not.toHaveBeenCalled();
    expect((button as HTMLButtonElement).disabled).toBe(true);
  });

  it("answers a press", () => {
    const pressed = vi.fn();
    render(<Button onClick={pressed}>Hifadhi</Button>);
    fireEvent.click(screen.getByRole("button", { name: "Hifadhi" }));
    expect(pressed).toHaveBeenCalledOnce();
  });
});
