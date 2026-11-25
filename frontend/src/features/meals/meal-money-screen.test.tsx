// meal-money-screen.test.tsx — Hela ya chakula (WAGE-7): the month's days, newest first, each with its money and how it
// is split, or that nobody typed it; the whole of the month, up to today; and the month moved back and forward, kept in
// the address.
import {
  act,
  fireEvent,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DAWA_LAPTOP_ANSWER, whoIsHere } from "@/test/devices";
import { answer, refusal, sent } from "@/test/fake-server";
import {
  mealDay,
  mealDays,
  type MealMoneyDays,
  row,
  TODAY,
  WITH_THE_KEY,
} from "@/test/meals";
import { render } from "@/test/render";
import { router } from "@/test/router";

import { MealMoneyScreen } from "./meal-money-screen";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

const ME = "/api/auth/me/";
const MEAL_MONEY = "/api/v1/staffpay/meal-money/";

/** Meneja is logged in; each span answers with its own days, or none. */
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

/** The spans the page asked the server for, in order. */
function spansAsked(): string[] {
  return sent
    .filter((request) => new URL(request.url).pathname === MEAL_MONEY)
    .map((request) => {
      const asked = new URL(request.url).searchParams;
      return `${asked.get("first") ?? ""} ${asked.get("last") ?? ""}`;
    });
}

/** A part's words, with the plain space people type for the one Intl writes after "TSh". */
function wordsOf(part: Element | null): string {
  return (part?.textContent ?? "").replace(/\u00a0/g, " ");
}

/** Back to the page, as a phone unlocked: the browser says it is visible again, and focused. */
function comeBack() {
  act(() => {
    document.dispatchEvent(new Event("visibilitychange", { bubbles: true }));
    window.dispatchEvent(new Event("focus"));
  });
}

/** The days' lines, each as its words. */
async function lines(): Promise<string[]> {
  const list = await screen.findByRole("list", { name: "Siku za mwezi" });
  return within(list)
    .getAllByRole("listitem")
    .map((line) => [...line.querySelectorAll("p")].map(wordsOf).join(" | "));
}

/** November as Jack drew it (24 Nov 2026). */
const NOVEMBER = mealDays(
  [
    mealDay({
      date: TODAY,
      amount: "9000.00",
      over: false,
      sharers: 0,
      share: "0.00",
    }),
    mealDay(),
    mealDay({ date: "2026-11-21", amount: "0.00", sharers: 6, share: "0.00" }),
    mealDay({
      date: "2026-11-20",
      amount: "7000.00",
      sharers: 7,
      share: "1000.00",
      waiting: 1,
    }),
  ],
  { total: "24000.00" },
);

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  // Tuesday 24 November 2026, noon in Arusha.
  vi.setSystemTime(new Date("2026-11-24T09:00:00Z"));
  window.history.replaceState(null, "", "/meal-money/");
});

afterEach(() => {
  vi.useRealTimers();
});

describe("the month's meal money", () => {
  it("lists this month's days as Jack drew them, newest first", async () => {
    theShopHas({ "2026-11-01 2026-11-30": NOVEMBER });

    render(<MealMoneyScreen />);

    expect(await lines()).toEqual([
      "Jumanne 24/11 (leo) | TSh 9,000 | Itagawanywa siku ikiisha",
      "Jumatatu 23/11 | TSh 8,000 | Watu 8 · TSh 1,000 kila mmoja",
      "Jumamosi 21/11 | Haijaandikwa",
      "Ijumaa 20/11 | TSh 7,000 | Watu 7 · TSh 1,000 kila mmoja | 1 anasubiri uamuzi",
    ]);
    expect(screen.getByRole("heading", { name: "Novemba 2026" })).toBeTruthy();
    expect(spansAsked()).toEqual(["2026-11-01 2026-11-30"]);
  });

  it("opens a day's own page from its line", async () => {
    theShopHas({ "2026-11-01 2026-11-30": NOVEMBER });

    render(<MealMoneyScreen />);

    const monday = await screen.findByRole("link", { name: "Jumatatu 23/11" });
    expect(monday.getAttribute("href")).toMatch(
      /^\/meal-money\/day\/?\?date=2026-11-23$/,
    );
    // Every day, a forgotten one and today too: that is where it is written.
    expect(screen.getAllByRole("link", { name: /\d\d\/11/ })).toHaveLength(4);
  });

  it("says the whole of the month, up to today", async () => {
    theShopHas({ "2026-11-01 2026-11-30": NOVEMBER });

    render(<MealMoneyScreen />);

    const total = await screen.findByText("Jumla hadi leo, 24/11");
    expect(wordsOf(total.parentElement)).toContain("TSh 24,000");
  });

  it("moves to the month before, kept in the address, and says its whole total", async () => {
    // October is over, so its total is the whole month's, not "up to today".
    theShopHas({
      "2026-11-01 2026-11-30": NOVEMBER,
      "2026-10-01 2026-10-31": mealDays(
        [mealDay({ date: "2026-10-30", amount: "6000.00", sharers: 6 })],
        { total: "6000.00" },
      ),
    });
    render(<MealMoneyScreen />);
    await lines();

    fireEvent.click(screen.getByRole("button", { name: "Mwezi uliopita" }));

    await screen.findByRole("heading", { name: "Oktoba 2026" });
    await waitFor(async () =>
      expect(await lines()).toEqual([
        "Ijumaa 30/10 | TSh 6,000 | Watu 6 · TSh 1,000 kila mmoja",
      ]),
    );
    expect(wordsOf(screen.getByText("Jumla").parentElement)).toContain(
      "TSh 6,000",
    );
    expect(window.location.search).toBe("?month=2026-10");
  });

  it("opens the month the address names, and this month for one to come or none", async () => {
    window.history.replaceState(null, "", "/meal-money/?month=2026-10");
    theShopHas({});
    const { unmount } = render(<MealMoneyScreen />);
    await screen.findByRole("heading", { name: "Oktoba 2026" });
    unmount();

    for (const asked of ["2026-12", "Novemba", "2026-1", "1999-12"]) {
      window.history.replaceState(null, "", `/meal-money/?month=${asked}`);
      const shown = render(<MealMoneyScreen />);
      await screen.findByRole("heading", { name: "Novemba 2026" });
      shown.unmount();
    }
  });

  it("asks for a month to its own last day, a leap February's too", async () => {
    window.history.replaceState(null, "", "/meal-money/?month=2024-02");
    theShopHas({});

    render(<MealMoneyScreen />);

    await waitFor(() =>
      expect(spansAsked()).toEqual(["2024-02-01 2024-02-29"]),
    );
  });

  it("says when a day's money is nobody's to share, and when it only waits", async () => {
    theShopHas({
      "2026-11-01 2026-11-30": mealDays([
        mealDay({ sharers: 0, share: "0.00" }),
        mealDay({ date: "2026-11-21", sharers: 0, share: "0.00", waiting: 2 }),
        mealDay({ date: "2026-11-20", sharers: 1, share: "8000.00" }),
      ]),
    });

    render(<MealMoneyScreen />);

    expect(await lines()).toEqual([
      "Jumatatu 23/11 | TSh 8,000 | Hakuna wa kuchangia",
      "Jumamosi 21/11 | TSh 8,000 | 2 wanasubiri uamuzi",
      "Ijumaa 20/11 | TSh 8,000 | Mtu 1 · TSh 8,000",
    ]);
  });

  it("never calls a day nobody came forgotten, its one row crossed out", async () => {
    // 7,000 typed on a Friday when nobody came, and crossed out: the day is still listed, for its row to be seen (A2),
    // but nobody forgot anything. A day someone came, or may have, is forgotten (WAGE-7's review).
    const slip = row({
      date: "2026-11-20",
      voided: {
        by: "Baba",
        at: "2026-11-20T16:00:00Z",
        reason: "Siku nyingine",
      },
    });
    theShopHas({
      "2026-11-01 2026-11-30": mealDays([
        mealDay({
          date: "2026-11-21",
          amount: "0.00",
          sharers: 0,
          share: "0.00",
          waiting: 1,
        }),
        mealDay({
          date: "2026-11-20",
          amount: "0.00",
          sharers: 0,
          share: "0.00",
          rows: [slip],
        }),
      ]),
    });

    render(<MealMoneyScreen />);

    expect(await lines()).toEqual([
      "Jumamosi 21/11 | Haijaandikwa",
      "Ijumaa 20/11 | TSh 0",
    ]);
  });

  it("says today is not written yet, before anyone types it", async () => {
    theShopHas({
      "2026-11-01 2026-11-30": mealDays([
        mealDay({
          date: TODAY,
          amount: "0.00",
          over: false,
          sharers: 0,
          share: "0.00",
        }),
      ]),
    });

    render(<MealMoneyScreen />);

    expect(await lines()).toEqual(["Jumanne 24/11 (leo) | Haijaandikwa"]);
  });

  it("says a month's pay is approved once every day of it is, and still types today's", async () => {
    window.history.replaceState(null, "", "/meal-money/?month=2026-10");
    theShopHas({
      "2026-10-01 2026-10-31": mealDays([mealDay({ date: "2026-10-31" })], {
        first: "2026-10-01",
        last: "2026-10-31",
        closed_to: "2026-10-31",
      }),
    });

    render(<MealMoneyScreen />);

    expect(
      await screen.findByText(
        "Malipo ya siku hizi yamefungwa, kwa hiyo hela ya chakula ya siku hizo haibadiliki tena.",
      ),
    ).toBeTruthy();
    expect(await lines()).toHaveLength(1);
    // Today's is still typed from any month: it is only the closed days that take none.
    expect(
      screen.getByRole("button", { name: "Andika hela ya chakula" }),
    ).toBeTruthy();
  });

  it("says nothing of it while a day shown is still open", async () => {
    // October is approved, and November, the month shown, is not.
    theShopHas({
      "2026-11-01 2026-11-30": { ...NOVEMBER, closed_to: "2026-10-31" },
    });

    render(<MealMoneyScreen />);

    await lines();
    expect(screen.queryByText(/yamefungwa/)).toBeNull();
  });

  it("says nothing of it on days chosen across the last approved one", async () => {
    // Two days of October, approved, and one of November, where a day's money can still be written.
    window.history.replaceState(
      null,
      "",
      "/meal-money/?first=2026-10-30&last=2026-11-02",
    );
    theShopHas({
      "2026-10-30 2026-11-02": mealDays([mealDay({ date: "2026-11-02" })], {
        first: "2026-10-30",
        last: "2026-11-02",
        closed_to: "2026-10-31",
      }),
    });

    render(<MealMoneyScreen />);

    await screen.findByRole("list", { name: "Siku ulizochagua" });
    expect(screen.queryByText(/yamefungwa/)).toBeNull();
  });

  it("says a month's pay is approved though nobody wrote any money in it", async () => {
    window.history.replaceState(null, "", "/meal-money/?month=2026-10");
    theShopHas({
      "2026-10-01 2026-10-31": mealDays([], {
        first: "2026-10-01",
        last: "2026-10-31",
        closed_to: "2026-10-31",
      }),
    });

    render(<MealMoneyScreen />);

    expect(await screen.findByText(/yamefungwa/)).toBeTruthy();
  });

  it("says when a month has none", async () => {
    theShopHas({});

    render(<MealMoneyScreen />);

    expect(
      await screen.findByText("Hakuna siku ya kuonyesha katika mwezi huu."),
    ).toBeTruthy();
  });

  it("shows only the server's refusal to someone without the key, with no month to move", async () => {
    // A manager who typed the address: the key is the owner's to give (Jack, 15 Nov 2026).
    answer("GET", ME, { status: 200, body: whoIsHere([]) });
    answer("GET", MEAL_MONEY, refusal(403, "permission_denied"));

    render(<MealMoneyScreen />);

    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Mwezi uliopita" })).toBeNull();
    expect(screen.queryByText(/Jumla/)).toBeNull();
  });

  it("shows money typed at once, the days asked again", async () => {
    // Baba types today's 9,000 from the list: the server's own new total and line, never one worked out on the phone.
    const before = mealDays([
      mealDay({
        date: TODAY,
        amount: "0.00",
        over: false,
        sharers: 0,
        share: "0.00",
      }),
    ]);
    theShopHas({ "2026-11-01 2026-11-30": before });
    render(<MealMoneyScreen />);
    expect(await lines()).toEqual(["Jumanne 24/11 (leo) | Haijaandikwa"]);

    answer("POST", MEAL_MONEY, {
      status: 201,
      body: row({ date: TODAY, amount: "9000.00" }),
    });
    theShopHas({ "2026-11-01 2026-11-30": NOVEMBER });
    fireEvent.click(
      screen.getByRole("button", { name: "Andika hela ya chakula" }),
    );
    const sheet = screen.getByRole("dialog");
    fireEvent.change(within(sheet).getByLabelText("Kiasi (TSh)"), {
      target: { value: "9000" },
    });
    fireEvent.click(within(sheet).getByRole("button", { name: "Hifadhi" }));

    await waitFor(async () => expect((await lines()).length).toBe(4));
    expect(screen.getByText(/^Imeandikwa: TSh/)).toBeTruthy();
  });

  it("offers nothing to type or choose to someone without the key", async () => {
    answer("GET", ME, { status: 200, body: whoIsHere([]) });
    answer("GET", MEAL_MONEY, refusal(403, "permission_denied"));

    render(<MealMoneyScreen />);

    await screen.findByRole("alert");
    expect(
      screen.queryByRole("button", { name: "Andika hela ya chakula" }),
    ).toBeNull();
    expect(screen.queryByRole("button", { name: "Chagua siku" })).toBeNull();
  });

  it.each([
    ["the office's home page, in a password's session", null, "/office/"],
    ["the PIN screen's welcome, on the shop's laptop", DAWA_LAPTOP_ANSWER, "/"],
  ])("sends the arrow from a fresh tab to %s", async (_where, device, home) => {
    vi.spyOn(window.history, "length", "get").mockReturnValue(1);
    theShopHas({ "2026-11-01 2026-11-30": NOVEMBER });
    answer("GET", ME, {
      status: 200,
      body: {
        ...WITH_THE_KEY,
        device: device?.device ?? null,
        home_side: device?.home_side ?? null,
      },
    });
    render(<MealMoneyScreen />);
    await lines();

    fireEvent.click(screen.getByRole("button", { name: "Rudi ulipotoka" }));

    expect(router.push).toHaveBeenCalledWith(home);
    vi.restoreAllMocks();
  });

  it("keeps the month last read when a later read fails, with the reason above it", async () => {
    theShopHas({ "2026-11-01 2026-11-30": NOVEMBER });
    render(<MealMoneyScreen />);
    await lines();
    answer("GET", MEAL_MONEY, refusal(403, "permission_denied"));
    vi.setSystemTime(new Date("2026-11-24T09:05:00Z"));

    comeBack();

    expect(await screen.findByRole("alert")).toBeTruthy();
    expect((await lines()).length).toBe(4);
  });
});
