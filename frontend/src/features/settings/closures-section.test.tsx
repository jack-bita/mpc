// closures-section.test.tsx — Siku duka limefungwa (ATT-9): the closures from today on, in the server's order,
// soonest first; a span written as its first and last day, one day as one date; a line when none is coming; the
// section in English; and why, when the server refuses the read.
import { screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { setLanguage } from "@/i18n/language";
import { closure, closuresAnswer } from "@/test/closures";
import { answer, refusal } from "@/test/fake-server";
import { render } from "@/test/render";

import { ClosuresSection } from "./closures-section";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

const CLOSURES = "/api/v1/shops/closures/";

// The card's example: the funeral, then the demo's next two public holidays, as the server sends them, soonest first.
const FUNERAL = closure();
const UHURU = closure({
  first_day: "2026-12-09",
  last_day: "2026-12-09",
  name: "Siku ya Uhuru",
});
const KRISMASI = closure({
  first_day: "2026-12-25",
  last_day: "2026-12-26",
  name: "Krismasi",
});

/** Each closure's line, its words run together as the screen shows them. Given 5 s, not Testing Library's 1, as the
 * first test of a file pays for the page's first load (settings-screen.test.tsx). */
async function linesShown(): Promise<string[]> {
  const list = await screen.findByRole("list", {}, { timeout: 5_000 });
  return within(list)
    .getAllByRole("listitem")
    .map((item) => item.textContent ?? "");
}

describe("Siku duka limefungwa", () => {
  it("lists each closure from today on, in the server's order, soonest first, with its name and its days", async () => {
    answer("GET", CLOSURES, {
      status: 200,
      body: closuresAnswer([FUNERAL, UHURU, KRISMASI]),
    });

    render(<ClosuresSection />);

    expect(await linesShown()).toEqual([
      "Msiba wa bibi20/11/2026 – 24/11/2026",
      // One day is one date, not "09/12/2026 – 09/12/2026".
      "Siku ya Uhuru09/12/2026",
      "Krismasi25/12/2026 – 26/12/2026",
    ]);
    expect(
      screen.getByRole("heading", { level: 2, name: "Siku duka limefungwa" }),
    ).toBeTruthy();
  });

  it("says so when no closure is coming, so an empty space never reads as a page still waiting", async () => {
    answer("GET", CLOSURES, { status: 200, body: closuresAnswer() });

    render(<ClosuresSection />);

    expect(
      await screen.findByText("Hakuna siku zijazo ambazo duka limefungwa."),
    ).toBeTruthy();
    expect(screen.queryByRole("list")).toBeNull();
  });

  it("says why when the server refuses the read", async () => {
    // A refusal the store doesn't try again (query-client.ts), as a server's own problem would be.
    answer("GET", CLOSURES, refusal(403, "permission_denied"));

    render(<ClosuresSection />);

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Huna ruhusa ya kufanya hili.",
    );
    expect(screen.queryByRole("list")).toBeNull();
  });

  it("speaks English for someone who reads English", async () => {
    setLanguage("en");
    answer("GET", CLOSURES, { status: 200, body: closuresAnswer([KRISMASI]) });

    render(<ClosuresSection />);

    // The name is the one the owner typed; the words around it are the book's.
    expect(await linesShown()).toEqual(["Krismasi25/12/2026 – 26/12/2026"]);
    expect(
      screen.getByRole("heading", {
        level: 2,
        name: "Days the shop is closed",
      }),
    ).toBeTruthy();
  });
});
