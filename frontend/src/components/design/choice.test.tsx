// choice.test.tsx — the choice piece: one pick at a time, a whole row to tap, its name, hint and error
// tied to the group, and edges and a focus ring that can be seen (UI-3, ADR-0039).
//
// jsdom paints nothing, so the colours are sums on the tokens in globals.css (src/test/look.ts), and
// seen by eye on /design.
import { fireEvent, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { colour, contrast } from "@/test/look";
import { render } from "@/test/render";

import { Choice, type ChoiceOption } from "./choice";

const SIDES: ChoiceOption[] = [
  { value: "d", label: "Dawa" },
  { value: "f", label: "Vyakula" },
];

/** A screen in miniature that keeps the pick, as a form does. */
function Picker(props: {
  hint?: string;
  error?: string;
  disabled?: boolean;
  onPick?: (value: string) => void;
}) {
  const [side, setSide] = useState<string | null>(null);
  return (
    <Choice
      label="Upande"
      options={SIDES}
      value={side}
      onValueChange={(value) => {
        setSide(value);
        props.onPick?.(value);
      }}
      hint={props.hint}
      error={props.error}
      disabled={props.disabled}
    />
  );
}

const radio = (name: string) => screen.getByRole("radio", { name });
const checked = (name: string) => radio(name).getAttribute("aria-checked");

describe("the choice", () => {
  it("is a group named by its label, with a radio named by each row's words", () => {
    render(<Picker />);

    expect(screen.getByRole("radiogroup", { name: "Upande" })).toBeDefined();
    expect(radio("Dawa")).toBeDefined();
    expect(radio("Vyakula")).toBeDefined();
    expect(checked("Dawa")).toBe("false");
  });

  it("picks one at a time, with a tap anywhere on the row", () => {
    const picked = vi.fn();
    render(<Picker onPick={picked} />);

    // The row's words, not the dot: the row is the finger's target.
    fireEvent.click(screen.getByText("Vyakula"));
    expect(picked).toHaveBeenLastCalledWith("f");
    expect(checked("Vyakula")).toBe("true");

    fireEvent.click(screen.getByText("Dawa"));
    expect(checked("Dawa")).toBe("true");
    expect(checked("Vyakula")).toBe("false");
  });

  it("ties its hint and its error to the group", () => {
    render(
      <Picker
        hint="Upande ambao kifaa kitahudumia zaidi"
        error="Chagua upande."
      />,
    );

    const group = screen.getByRole("radiogroup", { name: "Upande" });
    const describedBy = group.getAttribute("aria-describedby")?.split(" ");
    const said = describedBy?.map(
      (id) => document.getElementById(id)?.textContent,
    );
    expect(said).toEqual([
      "Upande ambao kifaa kitahudumia zaidi",
      "Chagua upande.",
    ]);
    expect(group.getAttribute("aria-invalid")).toBe("true");
  });

  it("says nothing extra while all is well", () => {
    render(<Picker />);

    const group = screen.getByRole("radiogroup", { name: "Upande" });
    expect(group.hasAttribute("aria-describedby")).toBe(false);
    expect(group.hasAttribute("aria-invalid")).toBe(false);
  });

  it("does nothing when switched off", () => {
    const picked = vi.fn();
    render(<Picker disabled onPick={picked} />);

    fireEvent.click(screen.getByText("Dawa"));

    expect(picked).not.toHaveBeenCalled();
    expect(checked("Dawa")).toBe("false");
  });

  it("is as tall as a big button, with a 24 px dot", () => {
    render(<Picker />);

    const row = screen.getByText("Dawa").closest("label");
    expect(row?.className.split(/\s+/)).toContain("min-h-(--control-big)");
    // The dot's size wins over shadcn's 16 px (size-4): cn() keeps the later one.
    const dot = radio("Dawa").className.split(/\s+/);
    expect(dot).toContain("size-6");
    expect(dot).not.toContain("size-4");
  });

  it("has edges that can be seen, picked or not", () => {
    // WCAG asks 3:1 of what shows a control: the row's edge and the dot's, on white.
    expect(
      contrast(colour("--input"), colour("--background")),
    ).toBeGreaterThanOrEqual(3);
    // Picked: the green edge, the green dot, and its white centre on the green.
    expect(
      contrast(colour("--primary"), colour("--background")),
    ).toBeGreaterThanOrEqual(3);
    expect(
      contrast(colour("--primary-foreground"), colour("--primary")),
    ).toBeGreaterThanOrEqual(3);
    render(<Picker />);
    const row = screen
      .getByText("Dawa")
      .closest("label")
      ?.className.split(/\s+/);
    expect(row).toContain("border-input");
    expect(row).toContain("has-data-checked:border-primary");
  });

  it("has its focus ring at full strength", () => {
    render(<Picker />);

    const dot = radio("Dawa").className.split(/\s+/);
    expect(dot).toContain("focus-visible:ring-ring");
    expect(dot).not.toContain("focus-visible:ring-ring/50");
    expect(
      contrast(colour("--ring"), colour("--background")),
    ).toBeGreaterThanOrEqual(3);
  });

  it("says a row in its own language, for a screen reader", () => {
    // Mipangilio yangu names each language in that language, as the bar's button does: "English" is said
    // as English, not read out with Swahili sounds (UI-9).
    render(
      <Choice
        label="Lugha"
        options={[
          { value: "sw", label: "Kiswahili", lang: "sw" },
          { value: "en", label: "English", lang: "en" },
        ]}
        value="sw"
        onValueChange={() => undefined}
      />,
    );

    expect(screen.getByText("English").getAttribute("lang")).toBe("en");
    expect(screen.getByText("Kiswahili").getAttribute("lang")).toBe("sw");
    // Still the dot's name: the words are inside its row's label.
    expect(radio("English")).toBeTruthy();
  });

  it("shows a row in its own font, so a person sees what they pick", () => {
    // A font's row is written in that font (UI-9). data-font changes the font only where font-sans is on
    // the same element (globals.css), so both are on the row's words.
    render(
      <Choice
        label="Herufi"
        options={[
          { value: "default", label: "Herufi ya kawaida", font: "default" },
          { value: "second", label: "Herufi ya pili", font: "second" },
        ]}
        value="default"
        onValueChange={() => undefined}
      />,
    );

    const second = screen.getByText("Herufi ya pili");
    expect(second.dataset.font).toBe("second");
    expect(second.className.split(/\s+/)).toContain("font-sans");
    expect(screen.getByText("Herufi ya kawaida").dataset.font).toBe("default");
  });

  it("leaves a row's words alone when it names no language or font", () => {
    render(<Picker />);

    const words = screen.getByText("Dawa");
    expect(words.hasAttribute("lang")).toBe(false);
    expect(words.hasAttribute("data-font")).toBe(false);
  });
});
