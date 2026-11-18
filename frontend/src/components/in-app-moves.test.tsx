// in-app-moves.test.tsx — the tab's note that the person moved between the app's own pages: set by a move
// inside the app, or by a page loaded from one of ours; never by a page opened fresh (page-header.tsx).
import { afterEach, describe, expect, it, vi } from "vitest";

import { render } from "@/test/render";

import { InAppMoves, MOVED_IN_APP, movedInApp } from "./in-app-moves";

// The address, as Next.js's router would give it; each test sets it.
const where = vi.hoisted(() => ({ path: "/office/" }));
vi.mock("next/navigation", async (importOriginal) => ({
  ...(await importOriginal<typeof import("next/navigation")>()),
  usePathname: () => where.path,
}));

/** Pretends the tab's history holds `pages` pages. */
function historyOf(pages: number) {
  vi.spyOn(window.history, "length", "get").mockReturnValue(pages);
}

/** Pretends this page was loaded whole from `from`, or from nowhere. */
function referrer(from: string) {
  vi.spyOn(document, "referrer", "get").mockReturnValue(from);
}

afterEach(() => {
  window.sessionStorage.clear();
  vi.restoreAllMocks();
  where.path = "/office/";
});

describe("the app's own moves", () => {
  it("are none on a page opened fresh, from a bookmark or a typed address", () => {
    referrer("");
    render(<InAppMoves />);
    expect(movedInApp()).toBe(false);
  });

  it("are none on a page opened from another website", () => {
    referrer("https://example.com/somewhere");
    render(<InAppMoves />);
    expect(movedInApp()).toBe(false);
  });

  it("count a move inside the app, as Next.js changes the address", () => {
    // A link or a push: a new address, and one more page in the tab's history, the one before it ours.
    referrer("");
    historyOf(1);
    const { rerender } = render(<InAppMoves />);
    where.path = "/settings/";
    historyOf(2);
    rerender(<InAppMoves />);
    expect(movedInApp()).toBe(true);
  });

  it("count no redirect, which changes the address and adds no page", () => {
    // A bookmark to /office/, opened from Chrome's new tab while logged out: the office sends the person
    // to /login/ with router.replace. The page before /login/ is Chrome's, not ours, so the arrow there
    // must not go back to it (OPS-13's review).
    referrer("");
    historyOf(2);
    const { rerender } = render(<InAppMoves />);
    where.path = "/login/";
    rerender(<InAppMoves />);
    expect(movedInApp()).toBe(false);
  });

  it("count a whole page loaded from one of the app's own, as a login's redirect", () => {
    referrer(`${window.location.origin}/login/`);
    render(<InAppMoves />);
    expect(movedInApp()).toBe(true);
  });

  it("are read as none when the browser refuses its storage", () => {
    window.sessionStorage.setItem(MOVED_IN_APP, "1");
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("refused");
    });
    expect(movedInApp()).toBe(false);
  });
});
