// page.test.tsx — the home page greets the user in Swahili, shows the app's version, and which device
// this is, or the way to register it (UI-3).
//
// The first Vitest test: it proves the test setup works end to end (TypeScript and JSX,
// the word books, jsdom, Testing Library). Later cards (REPO-4, OPS-1) check for
// this same word in the real browser. The English switch is checked in src/i18n/language.test.tsx.
import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { saveDevice } from "@/features/devices/this-device";
import { DAWA_LAPTOP } from "@/test/devices";
import { render } from "@/test/render";

import HomePage from "./page";

describe("HomePage", () => {
  it("says Karibu", () => {
    render(<HomePage />);

    // Find it the way a user, or a screen reader, finds it: the page's main heading, by
    // its words. The word itself is checked, not the message key, so a wrong translation
    // in messages/sw.json fails here too.
    const heading = screen.getByRole("heading", { level: 1 });
    expect(heading.textContent).toBe("Karibu");
  });

  it("shows the version this device runs", () => {
    render(<HomePage />);

    // Tests get no NEXT_PUBLIC_APP_VERSION, like any build outside the image: "dev" (src/lib/version.ts).
    expect(screen.getByText("Toleo dev")).toBeTruthy();
  });

  it("shows a new device the way to register it", () => {
    render(<HomePage />);

    const link = screen.getByRole("link", { name: "Sajili kifaa hiki" });
    // The end slash comes from next.config.ts (trailingSlash), which a test doesn't read.
    expect(link.getAttribute("href")).toMatch(/^\/register-device\/?$/);
  });

  it("shows a registered device its name and its shop, and no way to register", () => {
    saveDevice(DAWA_LAPTOP);

    render(<HomePage />);

    expect(screen.getByText("Laptop Dawa · MPC")).toBeTruthy();
    expect(
      screen.queryByRole("link", { name: "Sajili kifaa hiki" }),
    ).toBeNull();
  });
});
