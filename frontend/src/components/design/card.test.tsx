// card.test.tsx — the card wears the shop's corners and edge, not shadcn's (UI-8, ADR-0039).
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "./card";

function renderCard() {
  render(
    <Card data-testid="card">
      <CardHeader>
        <CardTitle>Jumla</CardTitle>
        <CardDescription>Mauzo ya leo</CardDescription>
      </CardHeader>
      <CardContent>41,000</CardContent>
      <CardFooter data-testid="footer">Imehifadhiwa</CardFooter>
    </Card>,
  );
  return {
    card: screen.getByTestId("card").className.split(/\s+/),
    footer: screen.getByTestId("footer").className.split(/\s+/),
  };
}

describe("the card", () => {
  it("has the shop's 8 px corners", () => {
    // --radius is 8 px, and rounded-lg reads it; shadcn's rounded-xl is 11 px.
    const { card } = renderCard();
    expect(card).toContain("rounded-lg");
    expect(card).not.toContain("rounded-xl");
  });

  it("has the pale line for an edge, not a see-through grey", () => {
    const { card } = renderCard();
    expect(card).toContain("ring-border");
    expect(card.filter((name) => /^ring-[\w-]+\/\d+/.test(name))).toEqual([]);
  });

  it("puts its footer on the whole pale panel", () => {
    // The text pairs in tokens.test.ts are checked on --muted itself, not on a half-faded one.
    const { footer } = renderCard();
    expect(footer).toContain("bg-muted");
    expect(footer).not.toContain("bg-muted/50");
  });

  it("keeps a two-line title close together", () => {
    renderCard();
    expect(screen.getByText("Jumla").className.split(/\s+/)).toContain(
      "leading-snug",
    );
  });

  it("shows every part", () => {
    renderCard();
    for (const text of ["Jumla", "Mauzo ya leo", "41,000", "Imehifadhiwa"])
      expect(screen.getByText(text)).toBeDefined();
  });
});
