// side-band.test.tsx — the side band shows a side by colour alone, from the shop's tokens (UI-8, ADR-0039).
import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TOKENS } from "@/test/look";

import { SIDE_BAND_LOOKS, SideBand, type SideBandLook } from "./side-band";

function band(look: SideBandLook): HTMLElement {
  const { container } = render(<SideBand look={look} />);
  return container.firstElementChild as HTMLElement;
}

describe("the side band", () => {
  it.each(SIDE_BAND_LOOKS)(
    "%s: colour only, hidden from screen readers",
    (look) => {
      // The side's name is in words in the top bar (UI-1), so a screen reader loses nothing here.
      const element = band(look);
      expect(element.getAttribute("aria-hidden")).toBe("true");
      expect(element.textContent).toBe("");
    },
  );

  it("paints blue with the blue token", () => {
    expect(band("blue").className.split(/\s+/)).toContain("bg-secondary");
  });

  it("draws the stripes from the faded red and the white, by name", () => {
    // By the tokens' names, never a hex of its own: a changed token must change the band too.
    const classes = band("striped").className;
    expect(classes).toContain("var(--destructive)");
    expect(classes).toContain("var(--background)");
    expect(classes).not.toMatch(/#[0-9a-f]{3,6}/i);
  });

  it.each(SIDE_BAND_LOOKS)(
    "%s: names only tokens that have a value",
    (look) => {
      // A misspelt name would paint nothing, and no error would say so.
      const names = [
        ...band(look).className.matchAll(/var\((--[\w-]+)\)/g),
      ].map((match) => match[1] ?? "");
      for (const name of names) expect(TOKENS.has(name), name).toBe(true);
    },
  );

  it("gives the two looks two different paints", () => {
    const paint = (look: SideBandLook) =>
      band(look)
        .className.split(/\s+/)
        .filter((name) => name.startsWith("bg-"));
    expect(paint("blue")).not.toEqual(paint("striped"));
  });
});
