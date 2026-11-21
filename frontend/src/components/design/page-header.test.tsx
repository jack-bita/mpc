// page-header.test.tsx — the top of a page: the title as its one heading, the words under it, an arrow
// that goes back to where the person was, but only to the app's own page: else to the office's home (Jack,
// 17 Nov 2026), and the page's one main button on the title's row (UI-11).
import { fireEvent, screen } from "@testing-library/react";
import { createRef } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { MOVED_IN_APP } from "@/components/in-app-moves";
import { render } from "@/test/render";
import { router } from "@/test/router";

import { ButtonLink } from "./button";
import { BACK_FALLBACK, PageHeader } from "./page-header";

/** Pretends the tab holds `pages` pages, this one last. */
function historyOf(pages: number) {
  vi.spyOn(window.history, "length", "get").mockReturnValue(pages);
}

/** Notes, as in-app-moves.tsx does, that the person came here from another of the app's pages. */
function movedInTheApp() {
  window.sessionStorage.setItem(MOVED_IN_APP, "1");
}

afterEach(() => {
  vi.restoreAllMocks();
  window.sessionStorage.clear();
});

describe("the page header", () => {
  it("shows the title as the page's heading, with its words under it", () => {
    render(<PageHeader title="Mipangilio ya duka" intro="Kanuni za duka." />);
    expect(
      screen.getByRole("heading", { level: 1, name: "Mipangilio ya duka" }),
    ).toBeDefined();
    expect(screen.getByText("Kanuni za duka.")).toBeDefined();
  });

  it("names the arrow in words, for a screen reader", () => {
    render(<PageHeader title="Mipangilio ya duka" />);
    expect(
      screen.getByRole("button", { name: "Rudi ulipotoka" }),
    ).toBeDefined();
  });

  it("goes back to where the person was, one of the app's pages", () => {
    historyOf(3);
    movedInTheApp();
    render(<PageHeader title="Mipangilio ya duka" />);
    fireEvent.click(screen.getByRole("button", { name: "Rudi ulipotoka" }));
    expect(router.back).toHaveBeenCalledOnce();
    expect(router.push).not.toHaveBeenCalled();
  });

  it("goes to the office's home from a tab with no page before this one", () => {
    historyOf(1);
    render(<PageHeader title="Mipangilio ya duka" />);
    fireEvent.click(screen.getByRole("button", { name: "Rudi ulipotoka" }));
    expect(router.back).not.toHaveBeenCalled();
    expect(router.push).toHaveBeenCalledWith(BACK_FALLBACK);
  });

  it("never goes back out of the app: a bookmark opened from Chrome's new tab", () => {
    // Chrome keeps its new-tab page in the tab's history: two pages, the first not ours.
    historyOf(2);
    render(<PageHeader title="Mipangilio ya duka" />);
    fireEvent.click(screen.getByRole("button", { name: "Rudi ulipotoka" }));
    expect(router.back).not.toHaveBeenCalled();
    expect(router.push).toHaveBeenCalledWith(BACK_FALLBACK);
  });

  it("goes where the page says, when it names its own way out", () => {
    historyOf(1);
    render(<PageHeader title="Ukurasa" fallback="/" />);
    fireEvent.click(screen.getByRole("button", { name: "Rudi ulipotoka" }));
    expect(router.push).toHaveBeenCalledWith("/");
  });

  it("goes back to the step before, for a step inside one page", () => {
    // The PIN pad, inside the home page: back to the tiles, never to another page (OPS-13).
    historyOf(3);
    movedInTheApp();
    const back = vi.fn();
    render(<PageHeader title="Asha Mfano" onBack={back} />);
    fireEvent.click(screen.getByRole("button", { name: "Rudi ulipotoka" }));
    expect(back).toHaveBeenCalledOnce();
    expect(router.back).not.toHaveBeenCalled();
    expect(router.push).not.toHaveBeenCalled();
  });

  it("holds the arrow while the page says so", () => {
    // A PIN on its way: its answer could still log the person in, behind the tiles the next one sees.
    const back = vi.fn();
    render(<PageHeader title="Asha Mfano" onBack={back} backDisabled />);
    const arrow = screen.getByRole("button", { name: "Rudi ulipotoka" });
    expect((arrow as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(arrow);
    expect(back).not.toHaveBeenCalled();
  });

  it("leaves the arrow out where the page says, and keeps the title", () => {
    // The clock-out's goodbye: she is on her way out, and the page logs her out by itself.
    render(<PageHeader title="Mahudhurio" arrow={false} />);
    expect(
      screen.getByRole("heading", { level: 1, name: "Mahudhurio" }),
    ).toBeDefined();
    expect(screen.queryByRole("button", { name: "Rudi ulipotoka" })).toBeNull();
  });

  it("lets a page focus its title, from code only", () => {
    const heading = createRef<HTMLHeadingElement>();
    render(<PageHeader title="Mipangilio yangu" headingRef={heading} />);
    expect(heading.current?.tagName).toBe("H1");
    // -1: focus by code, as a page arriving does; Tab passes it by.
    expect(heading.current?.getAttribute("tabindex")).toBe("-1");
  });

  it("puts the page's one action on the title's row, after the title", () => {
    // Wafanyakazi's Ongeza (UI-11): beside the title, at the top, whatever the list's length.
    render(
      <PageHeader
        title="Wafanyakazi"
        intro="Wanaofanya kazi dukani."
        action={<ButtonLink href="/workers/new/">Ongeza</ButtonLink>}
      />,
    );
    const title = screen.getByRole("heading", { level: 1 });
    const action = screen.getByRole("link", { name: "Ongeza" });
    // The same row as the title, and after it, so the arrow, the title and the button read in that order.
    const row = title.parentElement;
    expect(row?.contains(action)).toBe(true);
    expect(
      title.compareDocumentPosition(action) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    // Not under the intro: the intro is outside the row.
    expect(row?.contains(screen.getByText("Wanaofanya kazi dukani."))).toBe(
      false,
    );
  });

  it("draws nothing at the row's end for a page with no action", () => {
    render(<PageHeader title="Vifaa" />);
    const row = screen.getByRole("heading", { level: 1 }).parentElement;
    // The arrow and the title, nothing more.
    expect(row?.children).toHaveLength(2);
  });

  it("leaves the title out of focus when no page asks", () => {
    render(<PageHeader title="Vifaa" />);
    expect(
      screen.getByRole("heading", { level: 1 }).hasAttribute("tabindex"),
    ).toBe(false);
  });
});
