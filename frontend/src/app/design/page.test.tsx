// page.test.tsx — /design shows every colour, both fonts and every piece, in words from the message
// files (UI-8, ADR-0032, ADR-0039).
//
// What the pieces look like is checked by eye on the page itself; these tests check that nothing is
// missing from it, so a new colour or a new piece can't hide from that check.
import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SCREEN_BUTTON_KINDS } from "@/components/design/button";
import { TOKENS } from "@/test/look";
import { render } from "@/test/render";

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
    // Each screen kind: big, normal, switched off, and once more on the pale panel.
    for (const kind of SCREEN_BUTTON_KINDS)
      expect(
        screen.getAllByRole("button", { name: t.buttons[kind] }),
      ).toHaveLength(4);
    // One switched off for each screen kind, and one of the bar kind.
    const switchedOff = screen
      .getAllByRole("button")
      .filter((button) => (button as HTMLButtonElement).disabled);
    expect(switchedOff).toHaveLength(SCREEN_BUTTON_KINDS.length + 1);
  });

  it("shows the link that looks like a button, in each screen kind", () => {
    render(<DesignPage />);
    const links = screen.getAllByRole("link", { name: t.buttons.link });
    expect(links).toHaveLength(SCREEN_BUTTON_KINDS.length);
    for (const link of links) expect(link.tagName).toBe("A");
  });

  it("shows the bar kind on the bar's green, with a white focus ring", () => {
    render(<DesignPage />);
    // Big, normal and switched off.
    const onBar = screen.getAllByRole("button", { name: t.buttons.bar });
    expect(onBar).toHaveLength(3);
    // The strip they sit on sets --ring to white, as the top bar does (UI-1).
    const strip = onBar[0]?.parentElement;
    expect(strip?.classList.contains("bg-primary")).toBe(true);
    expect(
      strip?.classList.contains("[--ring:var(--primary-foreground)]"),
    ).toBe(true);
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

  it("shows a choice with a hint, one with an error and one switched off", () => {
    render(<DesignPage />);
    const groups = screen.getAllByRole("radiogroup", {
      name: t.choices.label,
    });
    expect(groups).toHaveLength(3);
    expect(groups[0]?.getAttribute("aria-describedby")).toBeTruthy();
    expect(groups[1]?.getAttribute("aria-invalid")).toBe("true");
    expect(groups[2]?.hasAttribute("data-disabled")).toBe(true);
  });

  it("shows both messages, a card and the top bar with both side bands", () => {
    const { container } = render(<DesignPage />);
    // Two status boxes: the info sample, and the live banner, empty while online.
    expect(screen.getAllByRole("status").map((box) => box.textContent)).toEqual(
      [expect.stringContaining(t.alerts.infoTitle), ""],
    );
    expect(screen.getByRole("alert").textContent).toContain(
      t.alerts.dangerTitle,
    );
    expect(screen.getByText(t.cards.cardTitle)).toBeDefined();
    const looks = [...container.querySelectorAll("[data-look]")].map((band) =>
      band.getAttribute("data-look"),
    );
    expect(looks).toEqual(["blue", "striped"]);
    // Each band under a real top bar that names its sample side in words.
    const bars = [...container.querySelectorAll("[data-look]")].map(
      (band) => band.closest("header")?.textContent,
    );
    expect(bars).toEqual([
      expect.stringContaining(`MPC · ${t.topBar.sampleSides.blue}`),
      expect.stringContaining(`MPC · ${t.topBar.sampleSides.striped}`),
    ]);
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
    // ADR-0040. A token's name, like --primary, is code and is shown as it is. Besides the page's own
    // words, the top bars show the language button's word and their sample places, "MPC · Dawa".
    const { container } = render(<DesignPage />);
    const places = Object.values(t.topBar.sampleSides).map((side) =>
      sw.topBar.place
        .replace("{shop}", t.topBar.sampleShop)
        .replace("{side}", side),
    );
    const allowed = new Set([...strings(t), sw.language.switch, ...places]);
    const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
    const strays: string[] = [];
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      const text = node.textContent?.trim() ?? "";
      if (text && !allowed.has(text) && !/^--[\w-]+$/.test(text))
        strays.push(text);
    }
    expect(strays).toEqual([]);
  });
});
