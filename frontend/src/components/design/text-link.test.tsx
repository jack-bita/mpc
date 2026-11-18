// text-link.test.tsx — TextLink is a real link to its page, underlined in the text's own colour, with the focus ring at
// full strength (PPL-6, ADR-0039).
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TextLink } from "./text-link";

describe("TextLink", () => {
  it("is a real link a screen reader names by its words", () => {
    render(<TextLink href="/workers/view/?id=1">Asha</TextLink>);

    const link = screen.getByRole("link", { name: "Asha" });
    // The slash before "?" comes from next.config.ts (trailingSlash), which a test doesn't read.
    expect(link.getAttribute("href")).toMatch(/^\/workers\/view\/?\?id=1$/);
  });

  it("reads as a link without a colour of its own, and rings at full strength", () => {
    render(<TextLink href="/workers/">Asha</TextLink>);

    const classes = screen.getByRole("link").className.split(" ");
    expect(classes).toEqual(
      expect.arrayContaining([
        "text-foreground",
        "underline",
        "focus-visible:ring-ring",
      ]),
    );
    // Never a faded ring (UI-1).
    expect(
      classes.some((name) => name.startsWith("focus-visible:ring-ring/")),
    ).toBe(false);
  });

  it("takes a screen's own classes beside its own", () => {
    render(
      <TextLink href="/workers/" className="after:absolute">
        Asha
      </TextLink>,
    );

    expect(screen.getByRole("link").className).toContain("after:absolute");
  });
});
