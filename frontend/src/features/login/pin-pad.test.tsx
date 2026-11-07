// pin-pad.test.tsx — the big PIN pad: a tap for each digit, or the laptop's number keys, and the 4th digit
// sends the PIN with no extra tap (UI-4, 03 §5.9). The tests play the person at the counter: they find
// each key by its name, as a screen reader does, and press it.
import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { setLanguage } from "@/i18n/language";
import { swahiliIn } from "@/test/language";
import { render } from "@/test/render";

import { PinPad } from "./pin-pad";

/** A finger on the key named `name`: a digit, or Futa. */
function tap(name: string) {
  fireEvent.click(screen.getByRole("button", { name }));
}

/** A key pressed on the laptop's keyboard, anywhere on the page. */
function press(key: string, held: Partial<KeyboardEventInit> = {}) {
  fireEvent.keyDown(window, { key, ...held });
}

/** The line a screen reader says as the dots fill: how many are typed, never which. */
function typedSoFar(count: number) {
  return screen.queryByText(`Umeandika tarakimu ${count} kati ya 4`);
}

describe("the pin pad", () => {
  it("sends the PIN when the 4th digit is tapped", () => {
    const sent = vi.fn();
    render(<PinPad onPin={sent} />);

    for (const digit of ["1", "9", "7", "3"]) tap(digit);

    expect(sent).toHaveBeenCalledOnce();
    expect(sent).toHaveBeenCalledWith("1973");
  });

  it("says how many digits are typed, and never shows which", () => {
    render(<PinPad onPin={vi.fn()} />);
    expect(typedSoFar(0)).not.toBeNull();

    tap("1");
    tap("9");

    expect(typedSoFar(2)).not.toBeNull();
    // The keys read 1 to 9, then 0, so "19" shows only if the pad printed what was typed: the next
    // person at the counter could read it.
    expect(document.body.textContent).not.toContain("19");
  });

  it("takes back the last digit with Futa", () => {
    const sent = vi.fn();
    render(<PinPad onPin={sent} />);

    // Futa with nothing typed takes nothing back, and breaks nothing.
    tap("Futa");
    tap("1");
    tap("2");
    tap("Futa");
    expect(typedSoFar(1)).not.toBeNull();
    for (const digit of ["3", "4", "5"]) tap(digit);

    expect(sent).toHaveBeenCalledWith("1345");
  });

  it("takes the laptop's number keys and Backspace", () => {
    // Laptops are keyboard first (03 §7): a seller types the PIN without reaching for the mouse.
    const sent = vi.fn();
    render(<PinPad onPin={sent} />);

    for (const key of ["4", "8", "Backspace", "2", "9", "7"]) press(key);

    expect(sent).toHaveBeenCalledWith("4297");
  });

  it("ignores other keys, a key held down, and keys pressed with Ctrl, Alt or Cmd", () => {
    // Ctrl+1 opens the browser's first tab, and a held key repeats by itself: neither is a digit typed.
    const sent = vi.fn();
    render(<PinPad onPin={sent} />);

    press("a");
    press("Enter");
    press("1", { repeat: true });
    press("2", { ctrlKey: true });
    press("3", { altKey: true });
    press("4", { metaKey: true });

    expect(typedSoFar(0)).not.toBeNull();
    expect(sent).not.toHaveBeenCalled();
  });

  it("starts empty again after sending, ready for the next try", () => {
    // A wrong PIN needs typing again from the start; the pad is ready the moment it has sent.
    const sent = vi.fn();
    render(<PinPad onPin={sent} />);

    for (const digit of ["1", "9", "7", "3"]) tap(digit);
    expect(typedSoFar(0)).not.toBeNull();
    for (const key of ["2", "0", "2", "6"]) press(key);

    expect(sent).toHaveBeenNthCalledWith(1, "1973");
    expect(sent).toHaveBeenNthCalledWith(2, "2026");
  });

  it("takes nothing while it is switched off, as a PIN is on its way", () => {
    const sent = vi.fn();
    render(<PinPad onPin={sent} disabled />);

    const keys = screen.getAllByRole("button") as HTMLButtonElement[];
    // Ten digits and Futa, all switched off.
    expect(keys).toHaveLength(11);
    for (const key of keys) expect(key.disabled).toBe(true);
    for (const key of ["1", "9", "7", "3"]) press(key);

    expect(typedSoFar(0)).not.toBeNull();
    expect(sent).not.toHaveBeenCalled();
  });

  it("has big keys, sized for a finger at the counter", () => {
    render(<PinPad onPin={vi.fn()} />);

    for (const key of screen.getAllByRole("button"))
      expect(key.className).toContain("h-(--control-big)");
  });

  it("speaks English after the switch, with no Swahili left", () => {
    setLanguage("en");
    const { container } = render(<PinPad onPin={vi.fn()} />);

    tap("Delete");
    tap("5");

    expect(screen.getByText("1 of 4 digits typed")).toBeDefined();
    expect(swahiliIn(container)).toEqual([]);
  });
});
