// top-bar.test.tsx — the top bar names the shop and side in words, keeps its text and focus ring
// readable on the green, and shows the side's band (UI-1, ADR-0039).
//
// jsdom paints nothing, so the colours are checked as sums on the tokens in globals.css (src/test/look.ts),
// and seen by eye on /design.
import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { colour, contrast } from "@/test/look";
import { render } from "@/test/render";

import { Button } from "./button";
import { ON_GREEN, TopBar } from "./top-bar";

const DAWA = { name: "Dawa", band: "blue" } as const;

describe("the top bar", () => {
  it("names the shop and the side in words", () => {
    render(<TopBar shop="MPC" side={DAWA} />);
    // In words, so nobody has to tell the band's colours apart (UI-8).
    expect(screen.getByRole("banner").textContent).toContain("MPC · Dawa");
  });

  it("names the shop alone while no side is known", () => {
    render(<TopBar shop="MPC" />);
    expect(screen.getByRole("banner").textContent).toBe("MPC");
  });

  it("names nothing while the app knows neither, and still shows its buttons", () => {
    // A device not yet registered, or a phone that is only a manager's own (UI-3).
    render(<TopBar actions={<Button kind="bar">Toka</Button>} />);
    expect(screen.getByRole("banner").textContent).toBe("Toka");
  });

  it("shows the side's band under it, hidden from screen readers", () => {
    const { container } = render(
      <TopBar shop="MPC" side={{ name: "Vyakula", band: "striped" }} />,
    );
    const band = container.querySelector("[data-look]");
    expect(band?.getAttribute("data-look")).toBe("striped");
    // Decoration: the side's name is already said in words (UI-8).
    expect(band?.getAttribute("aria-hidden")).toBe("true");
  });

  it("shows no band for a side whose look isn't known", () => {
    // No side says which look it gets yet (04 §20, item 19): words only (Jack, 7 Nov 2026).
    const { container } = render(<TopBar shop="MPC" side={{ name: "Dawa" }} />);
    expect(screen.getByRole("banner").textContent).toBe("MPC · Dawa");
    expect(container.querySelector("[data-look]")).toBeNull();
  });

  it("shows no band while no side is known", () => {
    // A band with no side would have to guess a look (04 §20, item 19).
    const { container } = render(<TopBar shop="MPC" />);
    expect(container.querySelector("[data-look]")).toBeNull();
  });

  it("is green, with its text readable on it", () => {
    render(<TopBar shop="MPC" side={DAWA} />);
    const bar = screen.getByText("MPC · Dawa").parentElement;
    for (const name of ON_GREEN.split(" "))
      expect(bar?.classList.contains(name)).toBe(true);
    expect(
      contrast(colour("--primary-foreground"), colour("--primary")),
    ).toBeGreaterThanOrEqual(4.5);
  });

  it("makes the focus ring white for everything on it", () => {
    // Our pieces read --ring (button.tsx). The blue ring reads at only 1.74:1 on the green.
    expect(ON_GREEN.split(" ")).toContain("[--ring:var(--primary-foreground)]");
    expect(contrast(colour("--ring"), colour("--primary"))).toBeLessThan(3);
    expect(
      contrast(colour("--primary-foreground"), colour("--primary")),
    ).toBeGreaterThanOrEqual(3);
  });

  it("puts its buttons inside the green, where the white ring applies", () => {
    render(<TopBar actions={<Button kind="bar">Toka</Button>} />);
    const button = screen.getByRole("button", { name: "Toka" });
    expect(button.closest(".bg-primary")).not.toBeNull();
  });
});
