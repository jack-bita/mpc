// page.test.tsx — the home page greets the user in Swahili.
//
// The first Vitest test: it proves the test setup works end to end (TypeScript and JSX,
// the JSON message files, jsdom, Testing Library). Later cards (REPO-4, OPS-1) check for
// this same word in the real browser.
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

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
});
