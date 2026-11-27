// sheet.test.tsx — the sheet piece: a short task over its own page, named for a screen reader, closed by Ghairi or
// Esc but never by a tap on the dimmed page (UI-10), sent by its main button or Enter, and held while its action is on
// its way (ADR-0039, ATT-6); and one that only shows, with Funga alone (WAGE-4).
//
// jsdom paints nothing, so where the sheet sits (the bottom, a phone's width on a wide screen) is checked by its
// classes here, and by eye on /design and a phone.
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { useRef, useState } from "react";
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

  it("stays open on a tap on the dimmed page, keeping what was typed (UI-10)", () => {
    const { onClose } = open();
    const box = screen.getByRole("textbox", { name: "Sababu" });
    fireEvent.change(box, { target: { value: "Alichelewa mara tatu" } });
    // The dimmed page behind the sheet: Base UI's backdrop, outside the dialog. A press is the whole tap, as a
    // finger's comes: down, up, then the click.
    const dimmed = document.querySelector('[data-slot="sheet-overlay"]');
    expect(dimmed).not.toBeNull();
    for (const press of [
      fireEvent.pointerDown,
      fireEvent.mouseDown,
      fireEvent.pointerUp,
      fireEvent.mouseUp,
      fireEvent.click,
    ])
      press(dimmed as Element);
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog")).toBeDefined();
    expect((box as HTMLInputElement).value).toBe("Alichelewa mara tatu");
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

  it("leaves the boxes' checks to the screen, which says them in the shop's words (UI-10)", () => {
    // A box's own limits (a last day's max) would stop the send with the browser's bubble, in the browser's language.
    open();
    const form = screen.getByRole("textbox").closest("form");
    expect(form?.noValidate).toBe(true);
  });

  it("draws its main button red for an action that is for good, as Ameondoka (UI-10)", () => {
    open({ actionKind: "danger", actionLabel: "Ameondoka" });
    const main = screen.getByRole("button", { name: "Ameondoka" });
    // The danger kind's look (button.tsx), and still the form's send.
    expect(main.className).toContain("text-destructive");
    expect(main.getAttribute("type")).toBe("submit");
  });

  it("gives the keyboard, as it closes, to what the screen names, or else back to where it was (UI-10)", async () => {
    // A screen whose sheet, once done, takes the button that opened it away (Simamisha becomes Rudisha) names its
    // done line; one that names nothing gets Base UI's own: back to the button.
    function Screen({ to }: { to: "line" | "nothing" }) {
      const [isOpen, setOpen] = useState(false);
      const line = useRef<HTMLParagraphElement>(null);
      return (
        <>
          <button type="button" onClick={() => setOpen(true)}>
            Fungua
          </button>
          <p ref={line} tabIndex={-1}>
            Imehifadhiwa.
          </p>
          <Sheet
            open={isOpen}
            onClose={() => setOpen(false)}
            onAction={() => setOpen(false)}
            title="Simamisha Asha"
            actionLabel="Simamisha"
            finalFocus={to === "line" ? () => line.current : undefined}
          >
            <input aria-label="Sababu" />
          </Sheet>
        </>
      );
    }

    const { unmount } = render(<Screen to="line" />);
    const opener = screen.getByRole("button", { name: "Fungua" });
    opener.focus();
    fireEvent.click(opener);
    fireEvent.click(await screen.findByRole("button", { name: "Simamisha" }));
    await waitFor(() =>
      expect(document.activeElement?.textContent).toBe("Imehifadhiwa."),
    );
    unmount();

    render(<Screen to="nothing" />);
    const again = screen.getByRole("button", { name: "Fungua" });
    again.focus();
    fireEvent.click(again);
    fireEvent.click(await screen.findByRole("button", { name: "Ghairi" }));
    await waitFor(() => expect(document.activeElement).toBe(again));
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

  // A sheet that only shows (WAGE-4): a worker's own day, with nothing to save.
  function onlyShows() {
    const onClose = vi.fn();
    render(
      <Sheet open onClose={onClose} title="Jumatano 04/11/2026">
        <p>Amechelewa · faini 500</p>
      </Sheet>,
    );
    return { onClose };
  }

  it("with nothing to save, has Funga alone, not Ghairi, and closes on it and on Esc (WAGE-4)", () => {
    const { onClose } = onlyShows();
    expect(
      screen.getByRole("dialog", { name: "Jumatano 04/11/2026" }),
    ).toBeDefined();
    // One button, which closes: Ghairi would say something is given up, and there is nothing to give up.
    expect(
      screen.getAllByRole("button").map((button) => button.textContent),
    ).toEqual(["Funga"]);
    fireEvent.click(screen.getByRole("button", { name: "Funga" }));
    expect(onClose).toHaveBeenCalledTimes(1);
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it("with nothing to save, sends nothing on Enter", () => {
    const { onClose } = onlyShows();
    // The form's own send, as Enter in it would make: no main action to run, and the sheet stays.
    fireEvent.submit(
      screen.getByRole("dialog").querySelector("form") as HTMLFormElement,
    );
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog")).toBeDefined();
  });

  it("says Funga in the open book's language", () => {
    setLanguage("en");
    render(
      <Sheet open onClose={() => undefined} title="Wednesday 04/11/2026">
        <p>Late · fine 500</p>
      </Sheet>,
    );
    expect(screen.getByRole("button", { name: "Close" })).toBeDefined();
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
