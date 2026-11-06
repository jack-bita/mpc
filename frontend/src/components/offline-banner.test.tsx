// offline-banner.test.tsx — office screens say Inahitaji mtandao while the network is gone, in a box a
// screen reader is sure to announce (UI-1, 03 §7.1).
//
// jsdom has no network to lose, so the tests play the browser's part: navigator.onLine answers what
// the test says, and an "online" or "offline" event tells the page it changed.
import { act, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import CounterLayout from "@/app/(counter)/layout";
import OfficeLayout from "@/app/(office)/layout";
import { setLanguage } from "@/i18n/language";
import { render } from "@/test/render";

import { OfflineBanner } from "./offline-banner";

/** Plays the browser: the network is now `state`, and the page is told, as the browser tells it. */
function network(state: "online" | "offline") {
  vi.spyOn(navigator, "onLine", "get").mockReturnValue(state === "online");
  act(() => {
    window.dispatchEvent(new Event(state));
  });
}

/** Whether the box is hidden from the eye: by its wrapper, as sr-only on the box would clash with
 * its own look (offline-banner.tsx). */
function hiding(box: HTMLElement): boolean {
  return box.parentElement?.classList.contains("sr-only") ?? false;
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("the offline banner", () => {
  it("keeps an empty box, hidden from the eye, while online", () => {
    render(<OfflineBanner />);

    // On the page, so a screen reader is already listening to it when the words come.
    const box = screen.getByRole("status");
    expect(box.textContent).toBe("");
    expect(hiding(box)).toBe(true);
  });

  it("says Inahitaji mtandao when the page opens with no network", () => {
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);

    render(<OfflineBanner />);

    const box = screen.getByRole("status");
    expect(box.textContent).toContain("Inahitaji mtandao");
    expect(box.textContent).toContain(
      "Ukurasa huu unafanya kazi ukiwa mtandaoni tu.",
    );
    expect(hiding(box)).toBe(false);
  });

  it("puts its words into the same box when the network drops", () => {
    render(<OfflineBanner />);
    const before = screen.getByRole("status");

    network("offline");

    // The same element, not a new one: a screen reader says a status box when its text changes, and
    // may say nothing of a box that appears with its text already in it (alert.tsx).
    expect(screen.getByRole("status")).toBe(before);
    expect(before.textContent).toContain("Inahitaji mtandao");
  });

  it("empties the box when the network comes back", () => {
    render(<OfflineBanner />);
    network("offline");

    network("online");

    const box = screen.getByRole("status");
    expect(box.textContent).toBe("");
    expect(hiding(box)).toBe(true);
  });

  it("speaks English when English is chosen", () => {
    setLanguage("en");
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);

    render(<OfflineBanner />);

    expect(screen.getByRole("status").textContent).toContain(
      "Needs the internet",
    );
  });
});

describe("the areas", () => {
  it("show the banner on office screens while offline", () => {
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);

    render(
      <OfficeLayout>
        <p>screen</p>
      </OfficeLayout>,
    );

    expect(screen.getByRole("status").textContent).toContain(
      "Inahitaji mtandao",
    );
    // Under the top bar, before the screen: the first thing read after the bar.
    expect(
      screen
        .getByRole("status")
        .compareDocumentPosition(screen.getByRole("main")),
    ).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
  });

  it("show no banner on counter screens, which work offline", () => {
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);

    render(
      <CounterLayout>
        <p>screen</p>
      </CounterLayout>,
    );

    expect(screen.queryByRole("status")).toBeNull();
  });
});
