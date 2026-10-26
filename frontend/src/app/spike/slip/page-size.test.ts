// page-size.test.ts — the paper is as long as the slip, never shorter (SPIKE-2).
//
// CSS has no page size "as long as the content" (`size: 80mm auto` is invalid, 04 v1.11), so the
// slip page measures the slip in pixels and turns that into millimetres for `@page { size }`.
// A pure function, so it is tested here without a browser.
import { describe, expect, it } from "vitest";

import { pageSizeFor } from "./page-size";

describe("pageSizeFor", () => {
  it("the page is as tall as the slip", () => {
    // In CSS, 96 px is one inch, which is 25.4 mm: 400 px is 105.83 mm, rounded up to 106.
    expect(pageSizeFor(400)).toBe("80mm 106mm");
  });

  it("rounds up, so the last line is never cut", () => {
    // 378 px is 100.01 mm. A page of 100 mm would be a hair too short, and Chrome would push
    // the very bottom of the slip onto a second page.
    expect(pageSizeFor(378)).toBe("80mm 101mm");
  });
});
