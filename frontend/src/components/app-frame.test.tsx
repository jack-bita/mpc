// app-frame.test.tsx — the counter and office areas put every screen under the green top bar, with the
// language button, and give the page its one <main> (UI-1, 03 §7.1).
import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import CounterLayout from "@/app/(counter)/layout";
import OfficeLayout from "@/app/(office)/layout";
import { swahiliIn } from "@/test/language";
import { render } from "@/test/render";

const AREAS = [
  ["counter", CounterLayout],
  ["office", OfficeLayout],
] as const;

describe.each(AREAS)("the %s area", (area, Layout) => {
  it("puts the screen under the top bar, in the page's one <main>", () => {
    const { container } = render(
      <Layout>
        <p>screen</p>
      </Layout>,
    );

    expect(container.querySelector(`[data-area="${area}"]`)).not.toBeNull();
    expect(screen.getByRole("banner")).toBeTruthy();
    expect(screen.getByRole("main").textContent).toBe("screen");
    // The bar comes first, so it is the first thing Tab and a screen reader reach.
    expect(
      screen
        .getByRole("banner")
        .compareDocumentPosition(screen.getByRole("main")),
    ).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
  });

  it("switches to English from the bar, with no Swahili left", () => {
    const { container } = render(
      <Layout>
        <p>screen</p>
      </Layout>,
    );

    fireEvent.click(screen.getByRole("button", { name: "English" }));

    expect(screen.getByRole("button", { name: "Kiswahili" })).toBeTruthy();
    expect(swahiliIn(container)).toEqual([]);
  });
});
