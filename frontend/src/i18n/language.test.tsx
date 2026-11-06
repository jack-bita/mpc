// language.test.tsx — Swahili opens first, the English switch changes every word on every screen at
// once, and this browser keeps the choice (UI-1, ADR-0032).
//
// The card's Done line, "switching to English changes every visible string", is checked on every page
// of the app: Vite finds them all, so a new page is checked without being listed here. A word typed
// straight into a screen fails the lint rule first (text-rule.test.ts).
/// <reference types="vite/client" />
import { act, screen } from "@testing-library/react";
import type { ComponentType } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import HomePage from "@/app/page";
import { swahiliIn } from "@/test/language";
import { render } from "@/test/render";

import { setLanguage, STORAGE_KEY } from "./language";

// Every page of the app, by its file: "../app/design/page.tsx". eager: loaded now, not on demand.
const PAGES = import.meta.glob<{ default: ComponentType }>(
  "../app/**/page.tsx",
  { eager: true },
);

const heading = () => screen.getByRole("heading", { level: 1 }).textContent;

afterEach(() => {
  vi.restoreAllMocks();
});

describe("the language", () => {
  it("opens in Swahili when nothing is saved", () => {
    render(<HomePage />);

    expect(heading()).toBe("Karibu");
    expect(document.documentElement.lang).toBe("sw");
  });

  it("switches every screen at once, and keeps the choice for the next visit", () => {
    const { unmount } = render(<HomePage />);

    // act: let React finish redrawing before the test looks at the page.
    act(() => setLanguage("en"));
    expect(heading()).toBe("Welcome");
    // A screen reader now speaks the page as English.
    expect(document.documentElement.lang).toBe("en");

    // A reload: the page opens again on the same browser.
    unmount();
    render(<HomePage />);
    expect(heading()).toBe("Welcome");
  });

  it("switches back to Swahili", () => {
    setLanguage("en");
    render(<HomePage />);

    act(() => setLanguage("sw"));

    expect(heading()).toBe("Karibu");
    expect(document.documentElement.lang).toBe("sw");
  });

  it("opens in Swahili when the saved choice is a language it doesn't know", () => {
    // Written by an older or newer version of the app, or by hand.
    window.localStorage.setItem(STORAGE_KEY, "fr");

    render(<HomePage />);

    expect(heading()).toBe("Karibu");
  });

  it("follows a switch made in another tab", () => {
    render(<HomePage />);

    // The other tab writes the choice; the browser then tells this tab with a "storage" event.
    act(() => {
      window.localStorage.setItem(STORAGE_KEY, "en");
      window.dispatchEvent(new StorageEvent("storage", { key: STORAGE_KEY }));
    });

    expect(heading()).toBe("Welcome");
  });

  it("still opens, in Swahili, when the browser refuses its storage", () => {
    // A browser set to block every site's storage throws on each read and write.
    const refuse = () => {
      throw new DOMException("Storage is blocked", "SecurityError");
    };
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(refuse);
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(refuse);

    render(<HomePage />);
    act(() => setLanguage("en"));

    // The switch can't be kept, so nothing changes, and nothing breaks.
    expect(heading()).toBe("Karibu");
  });
});

describe("every page in English", () => {
  it("finds the app's pages", () => {
    // If the pattern above stopped matching, the check below would pass on no pages at all.
    expect(Object.keys(PAGES)).toEqual(
      expect.arrayContaining(["../app/page.tsx", "../app/design/page.tsx"]),
    );
  });

  it.each(Object.entries(PAGES))("%s has no Swahili left", (_, page) => {
    setLanguage("en");
    const Page = page.default;

    const { container } = render(<Page />);

    expect(container.textContent?.trim()).not.toBe("");
    expect(swahiliIn(container)).toEqual([]);
  });
});
