// field.test.tsx — a field ties its label, hint and error to its box, and the box keeps the look
// (UI-8, ADR-0039).
//
// The ties are what a screen reader follows, so the tests find the box the way one does: by its label
// (getByLabelText), then by the ids it names. The look is checked on the classes the browser gets,
// as in button.test.tsx; seeing it is on /design.
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Field } from "./field";
import { Input, INPUT_SIZES } from "./input";

/** The text of each element the box names in aria-describedby, in order. */
function describedBy(box: HTMLElement): (string | null | undefined)[] {
  return (box.getAttribute("aria-describedby") ?? "")
    .split(" ")
    .filter(Boolean)
    .map((id) => document.getElementById(id)?.textContent);
}

describe("a field", () => {
  it("names its box with its label", () => {
    render(<Field label="Jina la mteja" />);
    expect(screen.getByLabelText("Jina la mteja").tagName).toBe("INPUT");
  });

  it("reads the hint and the error with the box", () => {
    render(
      <Field label="Simu" hint="Kama 0712 345 678" error="Namba si sahihi" />,
    );
    const box = screen.getByLabelText("Simu");
    expect(describedBy(box)).toEqual(["Kama 0712 345 678", "Namba si sahihi"]);
    // aria-invalid also paints the red edge (input.tsx).
    expect(box.getAttribute("aria-invalid")).toBe("true");
  });

  it("says nothing is wrong when nothing is", () => {
    // No aria-invalid="false" and no ids that point at nothing: both are noise to a screen reader.
    render(<Field label="Simu" />);
    const box = screen.getByLabelText("Simu");
    expect(box.hasAttribute("aria-invalid")).toBe(false);
    expect(box.hasAttribute("aria-describedby")).toBe(false);
  });

  it("names only the hint when there is no error", () => {
    render(<Field label="Simu" hint="Kama 0712 345 678" />);
    const box = screen.getByLabelText("Simu");
    expect(describedBy(box)).toEqual(["Kama 0712 345 678"]);
    expect(box.hasAttribute("aria-invalid")).toBe(false);
  });

  it("shows the error above the box, where a phone's keyboard can't cover it", () => {
    render(<Field label="Simu" error="Namba si sahihi" />);
    const error = screen.getByText("Namba si sahihi");
    const box = screen.getByLabelText("Simu");
    expect(
      error.compareDocumentPosition(box) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it("gives two fields on one screen their own ids", () => {
    render(
      <>
        <Field label="Jina" error="Weka jina" />
        <Field label="Simu" error="Weka namba ya simu" />
      </>,
    );
    const name = screen.getByLabelText("Jina");
    const phone = screen.getByLabelText("Simu");
    expect(name.id).not.toBe(phone.id);
    expect(describedBy(name)).toEqual(["Weka jina"]);
    expect(describedBy(phone)).toEqual(["Weka namba ya simu"]);
  });

  it("hands the box what a screen tells it", () => {
    // The kilo box at the counter: a number keypad on a phone, a value, switched off.
    render(
      <Field label="Kilo" inputMode="decimal" defaultValue="35.5" disabled />,
    );
    const box = screen.getByLabelText("Kilo") as HTMLInputElement;
    expect(box.inputMode).toBe("decimal");
    expect(box.value).toBe("35.5");
    expect(box.disabled).toBe(true);
  });
});

describe("the box's look", () => {
  function classesOf(props: Parameters<typeof Input>[0] = {}): string[] {
    render(<Input aria-label="Tafuta" {...props} />);
    return screen.getByLabelText("Tafuta").className.split(/\s+/);
  }

  it.each([
    ["big", "h-(--control-big)"],
    ["normal", "h-(--control-normal)"],
  ] as const)("%s: one height, %s", (size, height) => {
    // shadcn's h-8 must be gone, or CSS order would choose.
    expect(classesOf({ size }).filter((name) => /^h-/.test(name))).toEqual([
      height,
    ]);
  });

  it("is big unless told otherwise", () => {
    expect(INPUT_SIZES).toEqual(["big", "normal"]);
    expect(classesOf()).toContain("h-(--control-big)");
  });

  it("has the dark edge that says where to type", () => {
    // --input reads at 3:1 on white and on a pale panel (tokens.test.ts).
    expect(classesOf()).toContain("border-input");
  });

  it("keeps the focus ring at full strength, also with an error", () => {
    // Tailwind writes shadcn's aria-invalid:ring-destructive/20 after focus-visible:ring-ring, so only
    // the aria-invalid:focus-visible: form keeps the blue ring on a refused box you are typing in.
    const classes = classesOf();
    expect(classes).toContain("focus-visible:ring-ring");
    expect(classes).toContain("aria-invalid:focus-visible:ring-ring");
    expect(
      classes.filter((name) => /^focus-visible:ring-.*\//.test(name)),
    ).toEqual([]);
  });

  it("is pale, not grey, when switched off", () => {
    // --input is the dark edge colour now; shadcn's disabled:bg-input/50 would be a heavy grey.
    const classes = classesOf();
    expect(classes).toContain("disabled:bg-muted");
    expect(
      classes.filter((name) => name.startsWith("disabled:bg-input")),
    ).toEqual([]);
  });

  it("writes 16 px on every screen", () => {
    // Under 16 px, a phone's browser zooms in when the box is touched.
    const classes = classesOf();
    expect(classes).toContain("text-base");
    expect(classes).not.toContain("md:text-sm");
  });
});
