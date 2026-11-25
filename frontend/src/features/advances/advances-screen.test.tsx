// advances-screen.test.tsx — Advansi (WAGE-8): the month's money given to workers before payday, newest first, with its
// total, the crossed-out ones struck through; and the month moved back and forward, kept in the address.
import {
  act,
  fireEvent,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  advance,
  ADVANCES_ROUTE,
  type AdvancesMonth,
  advancesMonth,
  MENEJA,
} from "@/test/advances";
import { DAWA, whoIsHere } from "@/test/devices";
import { answer, refusal, sent } from "@/test/fake-server";
import { render } from "@/test/render";

import { AdvancesScreen } from "./advances-screen";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

const ME = "/api/auth/me/";

/** Meneja is logged in; each month answers with its own, or none. */
function theShopHas(months: Record<string, AdvancesMonth>) {
  answer("GET", ME, { status: 200, body: MENEJA });
  answer("GET", ADVANCES_ROUTE, (request) => {
    const month = new URL(request.url).searchParams.get("month") ?? "";
    return Response.json(months[month] ?? advancesMonth([], { month }));
  });
}

/** The months the page asked the server for, in order. */
function monthsAsked(): (string | null)[] {
  return sent
    .filter((request) => new URL(request.url).pathname === ADVANCES_ROUTE)
    .map((request) => new URL(request.url).searchParams.get("month"));
}

/** A part's words, with the plain space people type for the one Intl writes after "TSh". */
function wordsOf(part: Element | null): string {
  return (part?.textContent ?? "").replace(/ /g, " ");
}

/** Back to the page, as a phone unlocked: the browser says it is visible again, and focused. */
function comeBack() {
  act(() => {
    document.dispatchEvent(new Event("visibilitychange", { bubbles: true }));
    window.dispatchEvent(new Event("focus"));
  });
}

/** The lines, each as its words. */
async function lines(): Promise<string[]> {
  const list = await screen.findByRole("list", { name: "Advansi za mwezi" });
  return within(list)
    .getAllByRole("listitem")
    .map((line) => [...line.querySelectorAll("p")].map(wordsOf).join(" | "));
}

/** November as Jack drew it (25 Nov 2026). */
const NOVEMBER = advancesMonth(
  [
    advance(),
    advance({
      display_name: "Asha",
      date: "2026-11-16",
      amount: "30000.00",
    }),
    advance({ date: "2026-11-10" }),
  ],
  { total: "70000.00" },
);

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  // Wednesday 25 November 2026, noon in Arusha.
  vi.setSystemTime(new Date("2026-11-25T09:00:00Z"));
  window.history.replaceState(null, "", "/advances/");
});

afterEach(() => {
  vi.useRealTimers();
});

describe("the month's advances", () => {
  it("lists this month's as Jack drew them, newest first, with their total", async () => {
    theShopHas({ "2026-11": NOVEMBER });

    render(<AdvancesScreen />);

    expect(await lines()).toEqual([
      "Jumatano 25/11 · Juma | 20,000",
      "Jumatatu 16/11 · Asha | 30,000",
      "Jumanne 10/11 · Juma | 20,000",
    ]);
    expect(screen.getByRole("heading", { name: "Novemba 2026" })).toBeTruthy();
    expect(wordsOf(screen.getByText("Jumla").parentElement)).toBe(
      "Jumla TSh 70,000",
    );
    expect(monthsAsked()).toEqual(["2026-11"]);
  });

  it("opens each one's own page from its line", async () => {
    theShopHas({ "2026-11": NOVEMBER });

    render(<AdvancesScreen />);

    const link = await screen.findByRole("link", {
      name: "Jumatatu 16/11 · Asha",
    });
    expect(link.getAttribute("href")).toMatch(
      new RegExp(`^/advances/view/?\\?id=${NOVEMBER.rows[1]?.id ?? ""}$`),
    );
    expect(screen.getAllByRole("link", { name: /\d\d\/11/ })).toHaveLength(3);
  });

  it("strikes through one crossed out, and says so to a screen reader too", async () => {
    // 300,000 typed for 30,000: it stays on the page (A2), and the server's total leaves it out.
    theShopHas({
      "2026-11": advancesMonth(
        [
          advance({ date: "2026-11-16", amount: "30000.00" }),
          advance({
            date: "2026-11-16",
            amount: "300000.00",
            voided: {
              by: "Baba",
              at: "2026-11-16T09:00:00Z",
              reason: "Sifuri moja zaidi",
            },
          }),
        ],
        { total: "30000.00" },
      ),
    });

    render(<AdvancesScreen />);

    expect(await lines()).toEqual([
      "Jumatatu 16/11 · Juma | 30,000",
      "Jumatatu 16/11 · Juma | 300,000 | Imebatilishwa",
    ]);
    const struck = document.querySelectorAll("s");
    expect([...struck].map(wordsOf)).toEqual(["300,000"]);
    expect(wordsOf(screen.getByText("Jumla").parentElement)).toBe(
      "Jumla TSh 30,000",
    );
  });

  it("says when a month has none", async () => {
    theShopHas({});

    render(<AdvancesScreen />);

    expect(
      await screen.findByText("Hakuna advansi katika mwezi huu."),
    ).toBeTruthy();
    expect(screen.queryByText("Jumla")).toBeNull();
  });

  it("moves to the month before, kept in the address", async () => {
    theShopHas({
      "2026-11": NOVEMBER,
      "2026-10": advancesMonth([advance({ date: "2026-10-30" })], {
        month: "2026-10",
        total: "20000.00",
      }),
    });
    render(<AdvancesScreen />);
    await lines();

    fireEvent.click(screen.getByRole("button", { name: "Mwezi uliopita" }));

    await screen.findByRole("heading", { name: "Oktoba 2026" });
    await waitFor(async () =>
      expect(await lines()).toEqual(["Ijumaa 30/10 · Juma | 20,000"]),
    );
    expect(window.location.search).toBe("?month=2026-10");
  });

  it("opens the month the address names, and this month for one to come or none", async () => {
    window.history.replaceState(null, "", "/advances/?month=2026-10");
    theShopHas({});
    const { unmount } = render(<AdvancesScreen />);
    await screen.findByRole("heading", { name: "Oktoba 2026" });
    unmount();

    for (const asked of ["2026-12", "Novemba", "2026-1", "1999-12"]) {
      window.history.replaceState(null, "", `/advances/?month=${asked}`);
      const shown = render(<AdvancesScreen />);
      await screen.findByRole("heading", { name: "Novemba 2026" });
      shown.unmount();
    }
  });

  it("shows only the server's refusal to someone without the key, with no month to move", async () => {
    // A seller who typed the address. The key on Dawa alone opens nothing either: a worker's pay is the whole shop's.
    for (const permissions of [["sale.write"], ["money.advance"]]) {
      answer("GET", ME, {
        status: 200,
        body: whoIsHere([{ side: DAWA, permissions }]),
      });
      answer("GET", ADVANCES_ROUTE, refusal(403, "permission_denied"));

      const shown = render(<AdvancesScreen />);

      expect(await screen.findByRole("alert")).toBeTruthy();
      expect(
        screen.queryByRole("button", { name: "Mwezi uliopita" }),
      ).toBeNull();
      expect(screen.queryByText("Jumla")).toBeNull();
      shown.unmount();
    }
  });

  it("keeps the month last read when a later read fails, with the reason above it", async () => {
    theShopHas({ "2026-11": NOVEMBER });
    render(<AdvancesScreen />);
    await lines();
    answer("GET", ADVANCES_ROUTE, refusal(403, "permission_denied"));
    vi.setSystemTime(new Date("2026-11-25T09:05:00Z"));

    comeBack();

    expect(await screen.findByRole("alert")).toBeTruthy();
    expect((await lines()).length).toBe(3);
  });
});
