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

/** The colour classes after `prefix` ("" at rest, "hover:", "active:"), with the prefix taken off. */
function withPrefix(
  classes: string[],
  prefix: string,
  utility: "bg" | "text",
): string[] {
  return classes
    .filter((name) => name.startsWith(`${prefix}${utility}-`))
    .map((name) => name.slice(prefix.length + utility.length + 1))
    .filter((value) =>
      utility === "bg"
        ? // bg-clip-padding is about where the paint stops, not its colour.
          !value.startsWith("clip-")
        : // text-lg and text-base are sizes: only a token's name is a colour.
          TOKENS.has(`--${value}`),
    );
}

// Every state a finger or a mouse can put a button in, and the menu-open state an outline can take.
// shadcn's dark: classes are left out on purpose: they never apply, as no page has class="dark" (UI-7).
const STATES = ["", "hover:", "active:", "aria-expanded:"];

describe("the button's colours", () => {
  it.each(BUTTON_KINDS)(
    "%s: the text reads at 4.5:1 at rest, on hover and when pressed, on white and on a pale panel",
    (kind) => {
      const classes = classesOf({ kind });
      const [restText] = withPrefix(classes, "", "text");
      const restBackgrounds = withPrefix(classes, "", "bg");
      expect(restText, "a colour for the text").toBeDefined();
      for (const state of STATES) {
        // A state with no colour of its own keeps the colour it has at rest.
        const text = withPrefix(classes, state, "text")[0] ?? restText;
        const own = withPrefix(classes, state, "bg");
        const backgrounds = own.length ? own : restBackgrounds;
        for (const [where, behind] of BEHIND) {
          // No background at all: the button is see-through, and the screen shows.
          for (const background of backgrounds.length ? backgrounds : [null]) {
            const painted =
              background === null ? behind : paint(background, behind);
            const ratio = contrast(colour(`--${text}`), painted);
            expect(
              ratio,
              `${kind} ${state || "at rest"} on ${where}`,
            ).toBeGreaterThanOrEqual(4.5);
          }
        }
      }
    },
  );

  it("main darkens and never fades", () => {
    // White on green faded to 90% reads at only 4.17:1 (UI-7). A fade is the bg-primary/N form.
    const classes = classesOf({ kind: "main" });
    const backgrounds = STATES.flatMap((state) =>
      withPrefix(classes, state, "bg"),
    );
    expect(backgrounds.filter((value) => value.includes("/"))).toEqual([]);
    expect(classes).toContain(
      "hover:bg-[color-mix(in_srgb,var(--primary)_88%,black)]",
    );
  });

  it.each(["second", "danger"] as const)(
    "%s: a light tint, 5 in 100 at most",
    (kind) => {
      // The danger limit is the card's: --destructive on its own 10% tint, over a pale panel, reads at
      // only 4.21:1. The blue has room to spare, and keeps the same limit so the two outlines match.
      const classes = classesOf({ kind });
      const tints = STATES.flatMap((state) => withPrefix(classes, state, "bg"))
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
