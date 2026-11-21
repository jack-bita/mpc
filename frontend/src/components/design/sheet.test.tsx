// sheet.test.tsx — the sheet piece: a short task over its own page, named for a screen reader, closed by Ghairi, Esc
// or a tap outside, sent by its main button or Enter, and held while its action is on its way (ADR-0039, ATT-6).
//
// jsdom paints nothing, so where the sheet sits (the bottom, a phone's width on a wide screen) is checked by its
// classes here, and by eye on /design and a phone.
import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { setLanguage } from "@/i18n/language";
import { render } from "@/test/render";

import { Sheet, SHEET_LOOK } from "./sheet";

function open(props: Partial<Parameters<typeof Sheet>[0]> = {}) {
  const onClose = vi.fn();
  const onAction = vi.fn();
  render(
    <Sheet
      open
      onClose={onClose}
      onAction={onAction}
      title="Amua siku ya Juma"
      description="Alhamisi 12/11 · Ingia 07:50 asubuhi"
      actionLabel="Hifadhi uamuzi"
      {...props}
    >
      <label>
        Sababu
        <input />
      </label>
    </Sheet>,
  );
  return { onClose, onAction };
}

describe("the sheet", () => {
  it("shows nothing while closed", () => {
    open({ open: false });
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("opens as a dialog named by its title, with what it is about, its form and its two buttons", () => {
    open();
    // A screen reader says the title as it opens, then what it is about.
    const sheet = screen.getByRole("dialog", { name: "Amua siku ya Juma" });
    const describedBy = sheet.getAttribute("aria-describedby") ?? "";
    expect(document.getElementById(describedBy)?.textContent).toBe(
      "Alhamisi 12/11 · Ingia 07:50 asubuhi",
    );
    expect(screen.getByRole("textbox", { name: "Sababu" })).toBeDefined();
    // Ghairi first, the main button last, both in the sheet.
    const buttons = screen.getAllByRole("button");
    expect(buttons.map((button) => button.textContent)).toEqual([
      "Ghairi",
      "Hifadhi uamuzi",
    ]);
  });

  it("draws no corner ✕, whose word is shadcn's English: Ghairi closes it", () => {
    open();
    expect(screen.queryByRole("button", { name: "Close" })).toBeNull();
  });

  it("closes on Ghairi and on Esc, telling the screen", () => {
    const { onClose, onAction } = open();
    fireEvent.click(screen.getByRole("button", { name: "Ghairi" }));
    expect(onClose).toHaveBeenCalledTimes(1);
    fireEvent.keyDown(screen.getByRole("textbox"), { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(2);
    expect(onAction).not.toHaveBeenCalled();
  });

  it("sends by its main button, and by Enter in a box, as a form does", () => {
    const { onAction, onClose } = open();
    fireEvent.click(screen.getByRole("button", { name: "Hifadhi uamuzi" }));
    expect(onAction).toHaveBeenCalledTimes(1);
    fireEvent.submit(screen.getByRole("textbox"));
    expect(onAction).toHaveBeenCalledTimes(2);
    expect(onClose).not.toHaveBeenCalled();
  });

  it("holds both buttons while its action is on its way, and nothing closes it", () => {
    const { onAction, onClose } = open({ busy: true });
    for (const name of ["Ghairi", "Hifadhi uamuzi"]) {
      const button = screen.getByRole("button", { name });
      expect((button as HTMLButtonElement).disabled).toBe(true);
    }
    fireEvent.keyDown(screen.getByRole("textbox"), { key: "Escape" });
    fireEvent.submit(screen.getByRole("textbox"));
    expect(onClose).not.toHaveBeenCalled();
    expect(onAction).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog")).toBeDefined();
  });

  it("can hold its main button alone, leaving Ghairi free, as with no network", () => {
    const { onAction, onClose } = open({ actionDisabled: true });
    const main = screen.getByRole("button", { name: "Hifadhi uamuzi" });
    expect((main as HTMLButtonElement).disabled).toBe(true);
    fireEvent.submit(screen.getByRole("textbox"));
    expect(onAction).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Ghairi" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("says Ghairi in the open book's language", () => {
    setLanguage("en");
    render(
      <Sheet
        open
        onClose={() => undefined}
        onAction={() => undefined}
        title="Decide Juma's day"
        actionLabel="Save the decision"
      >
        <p>Form</p>
      </Sheet>,
    );
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDefined();
  });

  it("comes from the bottom, rounded at the top, never taller than most of the screen", () => {
    open();
    const sheet = screen.getByRole("dialog");
    expect(sheet.getAttribute("data-side")).toBe("bottom");
    for (const look of SHEET_LOOK.split(" ")) {
      expect(sheet.className).toContain(look);
    }
  });
});
