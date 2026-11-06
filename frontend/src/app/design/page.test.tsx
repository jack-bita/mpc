// page.test.tsx — /design shows every colour, both fonts and every piece, in words from the message
// files (UI-8, ADR-0032, ADR-0039).
//
// What the pieces look like is checked by eye on the page itself; these tests check that nothing is
// missing from it, so a new colour or a new piece can't hide from that check.
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { BUTTON_KINDS } from "@/components/design/button";
import { TOKENS } from "@/test/look";

import en from "../../../messages/en.json";
import sw from "../../../messages/sw.json";

import DesignPage from "./page";

const t = sw.design;

/** Every string under `value`, however deep. */
function strings(value: unknown): string[] {
  if (typeof value === "string") return [value];
  if (value !== null && typeof value === "object")
    return Object.values(value).flatMap(strings);
  return [];
}

/** Every key under `value`, as a path like "fields.phoneError". */
function keys(value: unknown, prefix = ""): string[] {
  if (value === null || typeof value !== "object") return [prefix];
  return Object.entries(value).flatMap(([key, inner]) =>
    keys(inner, prefix ? `${prefix}.${key}` : key),
  );
}

describe("the design page", () => {
  it("shows a swatch for every colour in globals.css, and for nothing else", () => {
    // Both ways: a new token with no swatch, or a swatch for a token that is gone, fails.
    const { container } = render(<DesignPage />);
    const shown = [...container.querySelectorAll("[data-token]")].map(
      (swatch) => swatch.getAttribute("data-token"),
    );
    const colours = [...TOKENS]
      .filter(([, value]) => /^#[0-9a-f]{6}$/.test(value))
      .map(([name]) => name);
    expect(colours.length).toBeGreaterThan(0);
    expect(shown.sort()).toEqual(colours.sort());
  });

  it("shows every kind of button in both sizes, switched off and on a pale panel", () => {
    render(<DesignPage />);
    // Each kind: big, normal, switched off, and once more on the pale panel.
    for (const kind of BUTTON_KINDS)
      expect(
        screen.getAllByRole("button", { name: t.buttons[kind] }),
      ).toHaveLength(4);
    const switchedOff = screen
      .getAllByRole("button")
      .filter((button) => (button as HTMLButtonElement).disabled);
    expect(switchedOff).toHaveLength(BUTTON_KINDS.length);
  });

  it("shows a box with a hint, one with an error and one switched off", () => {
    render(<DesignPage />);
    expect(
      screen.getByLabelText(t.fields.name).getAttribute("aria-describedby"),
    ).toBeTruthy();
    expect(
      screen.getByLabelText(t.fields.phone).getAttribute("aria-invalid"),
    ).toBe("true");
    expect(
      (screen.getByLabelText(t.fields.kilo) as HTMLInputElement).disabled,
    ).toBe(true);
    expect(screen.getByLabelText(t.fields.search).tagName).toBe("INPUT");
  });

  it("shows both messages, a card and both side bands", () => {
    const { container } = render(<DesignPage />);
    expect(screen.getByRole("status").textContent).toContain(
      t.alerts.infoTitle,
    );
    expect(screen.getByRole("alert").textContent).toContain(
      t.alerts.dangerTitle,
    );
    expect(screen.getByText(t.cards.cardTitle)).toBeDefined();
    const looks = [...container.querySelectorAll("[data-look]")].map((band) =>
      band.getAttribute("data-look"),
    );
    expect(looks).toEqual(["blue", "striped"]);
  });

  it.each(["default", "second"])(
    "shows the %s font where it can really change",
    (font) => {
      // data-font changes the font only where font-sans is on the same element (UI-7). The default
      // sample says so too, so it stays the default inside a page set to the second font (UI-9).
      const { container } = render(<DesignPage />);
      const sample = container.querySelector(`[data-font="${font}"]`);
      expect(sample?.classList.contains("font-sans")).toBe(true);
    },
  );

  it("takes all its words from the message files", () => {
    // ADR-0032. A token's name, like --primary, is code and is shown as it is.
    const { container } = render(<DesignPage />);
    const allowed = new Set(strings(t));
    const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
    const strays: string[] = [];
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      const text = node.textContent?.trim() ?? "";
      if (text && !allowed.has(text) && !/^--[\w-]+$/.test(text))
        strays.push(text);
    }
    expect(strays).toEqual([]);
  });

  it("has every word in English too", () => {
    // The page shows Swahili until UI-1's English switch; the English must be ready when it comes.
    expect(keys(en.design)).toEqual(keys(sw.design));
  });
});
