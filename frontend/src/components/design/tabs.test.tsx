// tabs.test.tsx — the tabs piece: one section open at a time, every section kept on the page while hidden,
// a row that scrolls rather than squeezes, and words and a focus ring that can be read (ADR-0039).
//
// jsdom paints nothing and lays nothing out, so the scrolling and the sticky row are checked by their
// classes here, and by eye on a phone; the colours are sums on the tokens (src/test/look.ts).
import { fireEvent, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { colour, contrast } from "@/test/look";
import { render } from "@/test/render";

import { Tabs, type TabSection } from "./tabs";

const SECTIONS: TabSection[] = [
  {
    value: "attendance",
    label: "Mahudhurio",
    content: <input aria-label="Saa" />,
  },
  { value: "money", label: "Pesa", content: <p>Kiasi cha pesa</p> },
  { value: "sides", label: "Pande", content: <p>Dawa na Vyakula</p> },
];

/** Whether a tab is the open one, as a screen reader hears it. */
function selected(name: string) {
  return screen.getByRole("tab", { name }).getAttribute("aria-selected");
}

/** Whether some words sit in a hidden panel: on the page, but neither seen nor read. */
function isHidden(text: string) {
  return screen.getByText(text).closest("[hidden]") !== null;
}

/** A screen in miniature that keeps the open section, as the settings page does. */
function Page({ onChange }: { onChange?: (value: string) => void }) {
  const [open, setOpen] = useState("attendance");
  return (
    <Tabs
      label="Mipangilio ya duka"
      sections={SECTIONS}
      value={open}
      onChange={(value) => {
        onChange?.(value);
        setOpen(value);
      }}
    />
  );
}

describe("the tabs", () => {
  it("names the row and shows a tab for each section, the open one selected", () => {
    render(<Page />);
    screen.getByRole("tablist", { name: "Mipangilio ya duka" });
    expect(screen.getAllByRole("tab").map((tab) => tab.textContent)).toEqual([
      "Mahudhurio",
      "Pesa",
      "Pande",
    ]);
    expect(selected("Mahudhurio")).toBe("true");
    // Only the open section is seen, named by its tab; the others stay on the page, hidden.
    screen.getByRole("tabpanel", { name: "Mahudhurio" });
    expect(isHidden("Kiasi cha pesa")).toBe(true);
  });

  it("opens a section when its tab is pressed, and tells the screen", () => {
    const onChange = vi.fn();
    render(<Page onChange={onChange} />);
    fireEvent.click(screen.getByRole("tab", { name: "Pesa" }));
    expect(onChange).toHaveBeenCalledWith("money");
    expect(selected("Pesa")).toBe("true");
    expect(isHidden("Kiasi cha pesa")).toBe(false);
  });

  it("keeps what was typed in a hidden section", () => {
    render(<Page />);
    fireEvent.change(screen.getByLabelText("Saa"), {
      target: { value: "07:30" },
    });
    fireEvent.click(screen.getByRole("tab", { name: "Pesa" }));
    fireEvent.click(screen.getByRole("tab", { name: "Mahudhurio" }));
    expect(screen.getByLabelText<HTMLInputElement>("Saa").value).toBe("07:30");
  });

  it("scrolls the row sideways, sticky at the top, never squeezing a tab", () => {
    render(<Page />);
    const row = screen.getByRole("tablist").className.split(/\s+/);
    expect(row).toEqual(
      expect.arrayContaining(["overflow-x-auto", "sticky", "top-0", "w-full"]),
    );
    // shadcn's 32 px row would cut the 44 px tabs: cn() must have swapped its height for ours.
    expect(row).toContain("group-data-horizontal/tabs:h-auto");
    expect(row).not.toContain("group-data-horizontal/tabs:h-8");
    const tab = screen
      .getByRole("tab", { name: "Pesa" })
      .className.split(/\s+/);
    expect(tab).toEqual(
      expect.arrayContaining(["flex-none", "min-h-(--control-normal)"]),
    );
  });

  it("never widens the page: the row scrolls inside it", () => {
    render(<Page />);
    // The root is a grid or flex child of the page; without min-w-0 it takes the row's full width.
    const root = screen.getByRole("tablist").closest("[data-slot=tabs]");
    expect(root?.className.split(/\s+/)).toContain("min-w-0");
  });

  it("draws every tab as a button with an edge", () => {
    render(<Page />);
    const tab = screen
      .getByRole("tab", { name: "Pesa" })
      .className.split(/\s+/);
    // The dark edge of the boxes (--input) and the buttons' corners: cn() must have swapped shadcn's
    // see-through edge and smaller corners for ours.
    expect(tab).toEqual(expect.arrayContaining(["border-input", "rounded-lg"]));
    expect(tab).not.toContain("border-transparent");
    expect(tab).not.toContain("rounded-md");
    // Not shadcn's "line" row: that one draws a line under the open tab, which would sit under the
    // green button as a second sign of the same thing.
    expect(screen.getByRole("tablist").getAttribute("data-variant")).toBe(
      "default",
    );
  });

  it("fills the open tab green with white words, kept under the mouse", () => {
    render(<Page />);
    const tab = screen
      .getByRole("tab", { name: "Pesa" })
      .className.split(/\s+/);
    expect(tab).toEqual(
      expect.arrayContaining([
        "data-active:border-primary",
        "data-active:bg-primary",
        "data-active:text-primary-foreground",
        "data-active:hover:text-primary-foreground",
      ]),
    );
    // shadcn's open tab is white with dark words: cn() must have swapped both for ours.
    expect(tab).not.toContain("data-active:bg-background");
    expect(tab).not.toContain("data-active:text-foreground");
  });

  it("turns the focus ring white on the open, green tab", () => {
    render(<Page />);
    const tab = screen
      .getByRole("tab", { name: "Pesa" })
      .className.split(/\s+/);
    // As ON_GREEN does for the top bar: the usual blue ring reads at only 1.74:1 on the green.
    expect(tab).toContain("data-active:[--ring:var(--primary-foreground)]");
    expect(
      contrast(colour("--primary-foreground"), colour("--primary")),
    ).toBeGreaterThanOrEqual(3);
  });

  it("has a full-strength focus ring, never shadcn's faded one", () => {
    render(<Page />);
    const tab = screen
      .getByRole("tab", { name: "Pesa" })
      .className.split(/\s+/);
    expect(tab).toContain("focus-visible:ring-ring");
    expect(tab).not.toContain("focus-visible:ring-ring/50");
  });

  it("shows a full-strength ring on the open section when Tab stops on it", () => {
    render(<Page />);
    const panel = screen.getByRole("tabpanel").className.split(/\s+/);
    expect(panel).toEqual(
      expect.arrayContaining([
        "focus-visible:ring-[3px]",
        "focus-visible:ring-ring",
      ]),
    );
  });

  it("scrolls the row, not the page, to bring the open tab into sight", () => {
    render(<Page />);
    const row = screen.getByRole("tablist");
    // jsdom lays nothing out: a 200 px row, each tab 120 px wide, side by side.
    Object.defineProperty(row, "clientWidth", { value: 200 });
    screen.getAllByRole("tab").forEach((tab, index) => {
      Object.defineProperty(tab, "offsetLeft", { value: index * 120 });
      Object.defineProperty(tab, "offsetWidth", { value: 120 });
    });
    const page = vi.spyOn(window, "scrollTo");

    fireEvent.click(screen.getByRole("tab", { name: "Pande" }));
    // Pande ends at 360 px: the row moves 160 px, so its right edge shows.
    expect(row.scrollLeft).toBe(160);
    fireEvent.click(screen.getByRole("tab", { name: "Mahudhurio" }));
    expect(row.scrollLeft).toBe(0);
    expect(page).not.toHaveBeenCalled();
  });

  it("has words and edges that can be read, at rest and open", () => {
    // At rest: --muted-foreground words on the screen's white, at least 4.5:1.
    expect(
      contrast(colour("--muted-foreground"), colour("--background")),
    ).toBeGreaterThanOrEqual(4.5);
    // Open: white words on the green, at least 4.5:1.
    expect(
      contrast(colour("--primary-foreground"), colour("--primary")),
    ).toBeGreaterThanOrEqual(4.5);
    // A closed tab's edge is what shows it is a button: at least the 3:1 WCAG asks of a control's edge.
    expect(
      contrast(colour("--input"), colour("--background")),
    ).toBeGreaterThanOrEqual(3);
  });
});
