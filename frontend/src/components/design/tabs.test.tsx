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

  it("has a full-strength focus ring, never shadcn's faded one", () => {
    render(<Page />);
    const tab = screen
      .getByRole("tab", { name: "Pesa" })
      .className.split(/\s+/);
    expect(tab).toContain("focus-visible:ring-ring");
    expect(tab).not.toContain("focus-visible:ring-ring/50");
  });

  it("has words that read on white, at rest and open", () => {
    // At rest --muted-foreground, open --primary: both at least 4.5:1 on the screen's white.
    expect(
      contrast(colour("--muted-foreground"), colour("--background")),
    ).toBeGreaterThanOrEqual(4.5);
    expect(
      contrast(colour("--primary"), colour("--background")),
    ).toBeGreaterThanOrEqual(4.5);
  });
});
