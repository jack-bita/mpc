// page-news.test.ts — the note a form's own page leaves for the worker's page it lands on (UI-11): read as that page
// draws, as many times as React draws it, until it is forgotten; the newest note winning.
import { describe, expect, it } from "vitest";

import { forgetNews, leaveNews, peekNews } from "./page-news";

describe("a form's page's note", () => {
  it("reads the same on every draw until it is forgotten, then nothing", () => {
    leaveNews({
      worker: "juma",
      card: "details",
      sentence: "Juma ameongezwa.",
    });

    // React may draw the page twice before it is on the screen: both draws find the note. The page itself, drawn so,
    // is worker-page.test.tsx's.
    expect(peekNews()?.sentence).toBe("Juma ameongezwa.");
    expect(peekNews()?.sentence).toBe("Juma ameongezwa.");
    forgetNews();
    expect(peekNews()).toBeNull();
  });

  it("keeps only the newest, as only one page is landed on", () => {
    leaveNews({ worker: "juma", card: "details", sentence: "Wa kwanza." });
    leaveNews({ worker: "asha", card: "roles", sentence: "Wa pili." });

    expect(peekNews()?.sentence).toBe("Wa pili.");
  });
});
