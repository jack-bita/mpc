// choose-days.test.tsx — Chagua siku (WAGE-7): the sheet where the days are chosen, and the list kept to them, with the
// whole of their money, in the address, until Mwezi mzima.
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { answer, sent } from "@/test/fake-server";
import {
  mealDay,
  mealDays,
  type MealMoneyDays,
  TODAY,
  WITH_THE_KEY,
} from "@/test/meals";
import { render } from "@/test/render";

import { MealMoneyScreen } from "./meal-money-screen";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

const ME = "/api/auth/me/";
const MEAL_MONEY = "/api/v1/staffpay/meal-money/";

/** Friday 20/11 to Monday 23/11, as Jack asked for them: 15,000. */
const CHOSEN: MealMoneyDays = mealDays(
  [mealDay(), mealDay({ date: "2026-11-20", amount: "7000.00", sharers: 7 })],
  { first: "2026-11-20", last: "2026-11-23", total: "15000.00" },
);

function theShopHas(spans: Record<string, MealMoneyDays>) {
  answer("GET", ME, { status: 200, body: WITH_THE_KEY });
  answer("GET", MEAL_MONEY, (request) => {
    const asked = new URL(request.url).searchParams;
    const first = asked.get("first") ?? "";
    const last = asked.get("last") ?? "";
    return Response.json(
      spans[`${first} ${last}`] ?? mealDays([], { first, last }),
    );
  });
}

function spansAsked(): string[] {
  return sent
    .filter((request) => new URL(request.url).pathname === MEAL_MONEY)
    .map((request) => {
      const asked = new URL(request.url).searchParams;
      return `${asked.get("first") ?? ""} ${asked.get("last") ?? ""}`;
    });
}

function wordsOf(part: Element | null): string {
  return (part?.textContent ?? "").replace(/ /g, " ");
}

/** The sheet, opened from the page. */
async function openTheSheet(): Promise<HTMLElement> {
  // Longer than the one second a find waits by itself: the file's first draw is slow on a busy machine.
  fireEvent.click(
    await screen.findByRole(
      "button",
      { name: "Chagua siku" },
      { timeout: 5000 },
    ),
  );
  return screen.findByRole("dialog", { name: "Chagua siku" });
}

function type(sheet: HTMLElement, label: string, value: string) {
  fireEvent.change(within(sheet).getByLabelText(label), { target: { value } });
}

function show(sheet: HTMLElement) {
  fireEvent.click(within(sheet).getByRole("button", { name: "Onyesha" }));
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  // Tuesday 24 November 2026, noon in Arusha.
  vi.setSystemTime(new Date("2026-11-24T09:00:00Z"));
  window.history.replaceState(null, "", "/meal-money/");
});

afterEach(() => {
  vi.useRealTimers();
});

describe("choosing the days", () => {
  it("shows the days chosen and the whole of them, kept in the address", async () => {
    // Meneja wants 20/11 to 23/11, and the whole total of it (Jack, 24 Nov 2026).
    theShopHas({ "2026-11-20 2026-11-23": CHOSEN });
    render(<MealMoneyScreen />);
    const sheet = await openTheSheet();

    type(sheet, "Kuanzia", "2026-11-20");
    type(sheet, "Hadi", "2026-11-23");
    show(sheet);

    expect(
      await screen.findByRole("heading", {
        name: "20/11/2026 hadi 23/11/2026",
      }),
    ).toBeTruthy();
    await waitFor(() =>
      expect(wordsOf(screen.getByText("Jumla").parentElement)).toBe(
        "Jumla TSh 15,000",
      ),
    );
    const list = screen.getByRole("list", { name: "Siku ulizochagua" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);
    expect(window.location.search).toBe("?first=2026-11-20&last=2026-11-23");
    // The month is not moved while days are chosen, and the sheet is gone.
    expect(screen.queryByRole("button", { name: "Mwezi uliopita" })).toBeNull();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("starts on this month so far, and on the days already chosen", async () => {
    theShopHas({ "2026-11-20 2026-11-23": CHOSEN });
    render(<MealMoneyScreen />);

    const sheet = await openTheSheet();

    const value = (label: string) =>
      (within(sheet).getByLabelText(label) as HTMLInputElement).value;
    expect([value("Kuanzia"), value("Hadi")]).toEqual(["2026-11-01", TODAY]);
    type(sheet, "Kuanzia", "2026-11-20");
    type(sheet, "Hadi", "2026-11-23");
    show(sheet);
    await screen.findByRole("heading", { name: "20/11/2026 hadi 23/11/2026" });

    const again = await openTheSheet();

    const second = (label: string) =>
      (within(again).getByLabelText(label) as HTMLInputElement).value;
    expect([second("Kuanzia"), second("Hadi")]).toEqual([
      "2026-11-20",
      "2026-11-23",
    ]);
  });

  it("starts on a month gone by to its own last day", async () => {
    window.history.replaceState(null, "", "/meal-money/?month=2026-10");
    theShopHas({});
    render(<MealMoneyScreen />);

    const sheet = await openTheSheet();

    const value = (label: string) =>
      (within(sheet).getByLabelText(label) as HTMLInputElement).value;
    expect([value("Kuanzia"), value("Hadi")]).toEqual([
      "2026-10-01",
      "2026-10-31",
    ]);
  });

  it("shows one day alone when both boxes hold it", async () => {
    theShopHas({
      "2026-11-23 2026-11-23": mealDays([mealDay()], {
        first: "2026-11-23",
        last: "2026-11-23",
        total: "8000.00",
      }),
    });
    render(<MealMoneyScreen />);
    const sheet = await openTheSheet();

    type(sheet, "Kuanzia", "2026-11-23");
    type(sheet, "Hadi", "2026-11-23");
    show(sheet);

    expect(
      await screen.findByRole("heading", { name: "23/11/2026" }),
    ).toBeTruthy();
  });

  it("goes back to the whole month, with the keyboard on Chagua siku", async () => {
    window.history.replaceState(
      null,
      "",
      "/meal-money/?month=2026-10&first=2026-11-20&last=2026-11-23",
    );
    theShopHas({ "2026-11-20 2026-11-23": CHOSEN });
    render(<MealMoneyScreen />);

    fireEvent.click(await screen.findByRole("button", { name: "Mwezi mzima" }));

    expect(
      await screen.findByRole("heading", { name: "Oktoba 2026" }),
    ).toBeTruthy();
    expect(window.location.search).toBe("?month=2026-10");
    expect(document.activeElement).toBe(
      screen.getByRole("button", { name: "Chagua siku" }),
    );
  });

  it.each([
    // What the address should never hold: no day, a day that doesn't exist, the last before the first, over a year.
    ["first=jana&last=2026-11-23"],
    ["first=2026-11-31&last=2026-12-01"],
    ["first=2026-11-23&last=2026-11-20"],
    ["first=2025-11-20&last=2026-11-23"],
    ["first=2026-11-20"],
    ["first=1999-12-31&last=2000-01-02"],
  ])("ignores days the address can't mean: %s", async (search) => {
    window.history.replaceState(null, "", `/meal-money/?${search}`);
    theShopHas({});

    render(<MealMoneyScreen />);

    await screen.findByRole("heading", { name: "Novemba 2026" });
    await waitFor(() =>
      expect(spansAsked()).toEqual(["2026-11-01 2026-11-30"]),
    );
  });

  it.each([
    ["2026-11-23", "2026-11-20", "Hadi", "Hadi iko kabla ya Kuanzia."],
    ["2025-11-20", "2026-11-23", "Hadi", "Chagua siku zisizozidi mwaka mmoja."],
    ["", "2026-11-23", "Kuanzia", "Jaza sehemu hii."],
    ["2026-11-20", "", "Hadi", "Jaza sehemu hii."],
    ["2026-11-25", "2026-11-26", "Kuanzia", "Siku hii bado haijafika."],
    ["2026-11-20", "2026-11-25", "Hadi", "Siku hii bado haijafika."],
  ])(
    "says a wrong pair beside its box, and asks nothing: %s to %s",
    async (first, last, box, sentence) => {
      theShopHas({});
      render(<MealMoneyScreen />);
      const sheet = await openTheSheet();
      const before = spansAsked();

      type(sheet, "Kuanzia", first);
      type(sheet, "Hadi", last);
      show(sheet);

      expect(
        (await within(sheet).findAllByText(sentence)).length,
      ).toBeGreaterThan(0);
      const described =
        within(sheet).getByLabelText(box).getAttribute("aria-describedby") ??
        "";
      expect(
        described
          .split(" ")
          .map((id) => document.getElementById(id)?.textContent),
      ).toContain(sentence);
      expect(spansAsked()).toEqual(before);
    },
  );

  it("leaves the list as it was on Ghairi", async () => {
    theShopHas({});
    render(<MealMoneyScreen />);
    const sheet = await openTheSheet();
    type(sheet, "Kuanzia", "2026-11-20");

    fireEvent.click(within(sheet).getByRole("button", { name: "Ghairi" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(window.location.search).toBe("");
    expect(screen.getByRole("heading", { name: "Novemba 2026" })).toBeTruthy();
  });

  it("says when the days chosen hold none", async () => {
    window.history.replaceState(
      null,
      "",
      "/meal-money/?first=2026-11-20&last=2026-11-23",
    );
    theShopHas({});

    render(<MealMoneyScreen />);

    expect(
      await screen.findByText("Hakuna siku ya kuonyesha katika siku hizi."),
    ).toBeTruthy();
  });

  it("says up to when it counted, when the address asks past today", async () => {
    // The server counts up to its own today: the heading says the days it counted, never the ones asked for.
    window.history.replaceState(
      null,
      "",
      "/meal-money/?first=2026-11-20&last=2026-11-30",
    );
    theShopHas({
      "2026-11-20 2026-11-30": mealDays([mealDay()], {
        first: "2026-11-20",
        last: TODAY,
      }),
    });

    render(<MealMoneyScreen />);

    expect(
      await screen.findByRole("heading", {
        name: "20/11/2026 hadi 24/11/2026",
      }),
    ).toBeTruthy();
  });
});
