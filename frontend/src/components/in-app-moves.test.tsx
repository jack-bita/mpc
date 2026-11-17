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
    referrer("");
    const { rerender } = render(<InAppMoves />);
    where.path = "/settings/";
    rerender(<InAppMoves />);
    expect(movedInApp()).toBe(true);
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
