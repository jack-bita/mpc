// pay-screen.test.tsx — Mishahara (WAGE-2): a line per worker with their total, what isn't paid said under the name, the
// whole of it, how far the month is counted, and the month moved back and forward, kept in the address.
import {
  act,
  fireEvent,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DAWA, whoIsHere } from "@/test/devices";
import { answer, refusal, sent } from "@/test/fake-server";
import {
  NO_PAY,
  OWNER,
  pay,
  PAY_ROUTE,
  type PayMonth,
  payMonth,
  workerPay,
} from "@/test/pay";
import { render } from "@/test/render";

import { PayScreen } from "./pay-screen";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

const ME = "/api/auth/me/";

/** Baba is logged in; each month answers with its own pay, or nobody's. */
function theShopPays(months: Record<string, PayMonth>) {
  answer("GET", ME, { status: 200, body: OWNER });
  answer("GET", PAY_ROUTE, (request) => {
    const month = new URL(request.url).searchParams.get("month") ?? "";
    return Response.json(months[month] ?? payMonth([], { month }));
  });
}

/** The months the page asked the server for, in order. */
function monthsAsked(): string[] {
  return sent
    .filter((request) => new URL(request.url).pathname === PAY_ROUTE)
    .map((request) => new URL(request.url).searchParams.get("month") ?? "");
}

/** A part's words, with the plain space people type for the one Intl writes after "TSh". */
function wordsOf(part: Element | null): string {
  return (part?.textContent ?? "").replace(/ /g, " ");
}

/** The workers' lines, each as its words. */
async function lines(): Promise<string[]> {
  const list = await screen.findByRole("list", {
    name: "Malipo ya kila mfanyakazi",
  });
  return within(list)
    .getAllByRole("listitem")
    .map((line) => [...line.querySelectorAll("p")].map(wordsOf).join(" | "));
}

/** November as Jack drew it (25 Nov 2026). */
const NOVEMBER = payMonth(
  [
    workerPay({ display_name: "Asha", total: "152000.00" }),
    workerPay({ display_name: "Baraka", total: "148000.00" }),
    workerPay({ display_name: "Juma", pay: pay({ waiting: 1 }) }),
    workerPay({
      display_name: "Neema",
      left_on: "2026-11-14",
      total: "60000.00",
    }),
  ],
  { total: "492000.00" },
);

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  // Wednesday 25 November 2026, noon in Arusha.
  vi.setSystemTime(new Date("2026-11-25T09:00:00Z"));
  window.history.replaceState(null, "", "/pay/");
});

afterEach(() => {
  vi.useRealTimers();
});

describe("the month's pay", () => {
  it("lists everyone as Jack drew it, with the whole of it", async () => {
    theShopPays({ "2026-11": NOVEMBER });

    render(<PayScreen />);

    expect(await lines()).toEqual([
      "Asha | 152,000",
      "Baraka | 148,000",
      "Juma | 132,000 | ! Siku 1 inasubiri uamuzi",
      "Neema | 60,000 | Aliondoka 14/11/2026",
    ]);
    expect(screen.getByRole("heading", { name: "Mishahara" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Novemba 2026" })).toBeTruthy();
    expect(screen.getByText("Hadi jana, Jumanne 24/11")).toBeTruthy();
    expect(wordsOf(screen.getByText("Jumla ya wote").parentElement)).toBe(
      "Jumla ya wote TSh 492,000",
    );
    expect(monthsAsked()).toEqual(["2026-11"]);
  });

  it("says under the name what isn't paid, and today", async () => {
    // Asha tapped Toka, so today is in her total; Baraka's Toka at 16:00 waits; Juma has days with no daily pay, and
    // several that wait; Neema tapped Toka and left tonight.
    theShopPays({
      "2026-11": payMonth([
        workerPay({
          display_name: "Asha",
          today: pay({ total: "10000.00" }),
          total: "162000.00",
        }),
        workerPay({
          display_name: "Baraka",
          today: { ...NO_PAY, waiting: 1 },
          total: "148000.00",
        }),
        workerPay({
          display_name: "Juma",
          pay: pay({ waiting: 3, no_rate: 2 }),
        }),
        workerPay({
          display_name: "Neema",
          today: pay({ total: "10000.00" }),
          left_on: "2026-11-25",
          total: "70000.00",
        }),
        workerPay({
          display_name: "Zawadi",
          pay: pay({ no_rate: 1 }),
          total: "-1500.00",
        }),
      ]),
    });

    render(<PayScreen />);

    expect(await lines()).toEqual([
      "Asha | 162,000 | Pamoja na leo",
      "Baraka | 148,000 | ! Leo inasubiri uamuzi",
      "Juma | 132,000 | ! Siku 3 zinasubiri uamuzi | ! Siku 2 hazina malipo kwa siku",
      "Neema | 70,000 | Pamoja na leo | Aliondoka 25/11/2026",
      "Zawadi | -1,500 | ! Siku 1 haina malipo kwa siku",
    ]);
  });

  it("opens a worker's own pay, the same month, from their line", async () => {
    // Two jobs of one person in the month are two lines, each opening its own.
    const first = workerPay({ display_name: "Juma", left_on: "2026-10-09" });
    const again = workerPay({ display_name: "Juma" });
    window.history.replaceState(null, "", "/pay/?month=2026-10");
    theShopPays({
      "2026-10": payMonth([first, again], { month: "2026-10" }),
    });

    render(<PayScreen />);

    const names = await screen.findAllByRole("link", { name: "Juma" });
    expect(names.map((name) => name.getAttribute("href"))).toEqual([
      expect.stringMatching(
        new RegExp(`^/pay/worker/?\\?staff=${first.staff}&month=2026-10$`),
      ),
      expect.stringMatching(
        new RegExp(`^/pay/worker/?\\?staff=${again.staff}&month=2026-10$`),
      ),
    ]);
  });

  it("hides the ! from a screen reader, which the words already say", async () => {
    theShopPays({ "2026-11": NOVEMBER });

    render(<PayScreen />);

    const note = await screen.findByText("Siku 1 inasubiri uamuzi");
    expect(
      within(note).getByText("!").getAttribute("aria-hidden"),
    ).not.toBeNull();
  });

  it("moves to the month before, kept in the address, counted to its end", async () => {
    // October is over, so nothing says how far it is counted.
    theShopPays({
      "2026-11": NOVEMBER,
      "2026-10": payMonth(
        [workerPay({ display_name: "Halima", total: "90000.00" })],
        { month: "2026-10", counted_to: "2026-10-31", total: "90000.00" },
      ),
    });
    render(<PayScreen />);
    await lines();

    fireEvent.click(screen.getByRole("button", { name: "Mwezi uliopita" }));

    await screen.findByRole("heading", { name: "Oktoba 2026" });
    await waitFor(async () =>
      expect(await lines()).toEqual(["Halima | 90,000"]),
    );
    expect(screen.queryByText(/Hadi jana/)).toBeNull();
    expect(window.location.search).toBe("?month=2026-10");
  });

  it("opens the month the address names, and this month for one to come or none", async () => {
    window.history.replaceState(null, "", "/pay/?month=2026-10");
    theShopPays({});
    const { unmount } = render(<PayScreen />);
    await screen.findByRole("heading", { name: "Oktoba 2026" });
    unmount();

    for (const asked of ["2026-12", "Novemba", "2026-1", "1999-12"]) {
      window.history.replaceState(null, "", `/pay/?month=${asked}`);
      const shown = render(<PayScreen />);
      await screen.findByRole("heading", { name: "Novemba 2026" });
      shown.unmount();
    }
  });

  it("says on the 1st that no day is over yet, above who works today", async () => {
    vi.setSystemTime(new Date("2026-12-01T05:00:00Z"));
    theShopPays({
      "2026-12": payMonth(
        [workerPay({ display_name: "Asha", pay: NO_PAY, total: "0.00" })],
        { month: "2026-12", today: "2026-12-01", counted_to: null },
      ),
    });

    render(<PayScreen />);

    expect(await lines()).toEqual(["Asha | 0"]);
    expect(
      screen.getByText("Bado hakuna siku ya kazi iliyokwisha mwezi huu."),
    ).toBeTruthy();
    expect(screen.queryByText(/Hadi jana/)).toBeNull();
  });

  it("says only that no day is over yet when the 1st is a Sunday or a closed day, and on the 2nd a Sunday", async () => {
    // Friday 1 January 2027 is a holiday: ten workers have a rate, and none is listed for want of a working day. "Hakuna
    // mfanyakazi anayelipwa kwa siku" would be untrue (the review). On the 2nd of a month whose 1st was closed and 2nd a
    // Sunday, a day is counted, and still none was worked.
    for (const [today, counted_to] of [
      ["2027-01-01", null],
      ["2027-05-02", "2027-05-01"],
    ] as const) {
      vi.setSystemTime(new Date(`${today}T05:00:00Z`));
      const month = today.slice(0, 7);
      theShopPays({
        [month]: payMonth([], { month, today, counted_to, no_day_yet: true }),
      });

      const shown = render(<PayScreen />);

      expect(
        await screen.findByText(
          "Bado hakuna siku ya kazi iliyokwisha mwezi huu.",
        ),
      ).toBeTruthy();
      expect(screen.queryByText(/Hakuna mfanyakazi|Hadi jana/)).toBeNull();
      shown.unmount();
    }
  });

  it("reads which month it is from the server's two answers, not the phone's date", async () => {
    // A phone a month behind still shows November as the server's own month gone by: no "Hadi jana".
    theShopPays({
      "2026-11": { ...NOVEMBER, today: "2026-12-02", counted_to: "2026-11-30" },
    });

    render(<PayScreen />);

    await lines();
    expect(screen.queryByText(/Hadi jana/)).toBeNull();
  });

  it("says when the shop pays nobody by the day, with no total", async () => {
    theShopPays({});

    render(<PayScreen />);

    expect(
      await screen.findByText(
        "Hakuna mfanyakazi anayelipwa kwa siku katika mwezi huu.",
      ),
    ).toBeTruthy();
    expect(screen.queryByText("Jumla ya wote")).toBeNull();
  });

  it("asks this month again by itself, so a Toka shows", async () => {
    // Baba opens the page at 18:40; Asha's Toka comes at 18:45, and a minute later the page has her Leo.
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(new Date("2026-11-25T15:40:00Z"));
    theShopPays({ "2026-11": NOVEMBER });
    render(<PayScreen />);
    await lines();
    expect(monthsAsked()).toHaveLength(1);

    await act(() => vi.advanceTimersByTimeAsync(61_000));

    await waitFor(() => expect(monthsAsked()).toHaveLength(2));
  });

  it("shows only the server's refusal to someone without both keys, with no month to move", async () => {
    // A manager who typed the address, and one handed the rules' key alone: the pay asks both (Jack, WAGE-1).
    for (const keys of [[], ["settings.manage"], ["staff.manage"]]) {
      answer("GET", ME, {
        status: 200,
        body: {
          ...whoIsHere([]),
          permissions: {
            whole_shop: keys,
            sides: [{ ...DAWA, permissions: keys }],
          },
        },
      });
      answer("GET", PAY_ROUTE, refusal(403, "permission_denied"));

      const shown = render(<PayScreen />);

      expect(await screen.findByRole("alert")).toBeTruthy();
      expect(
        screen.queryByRole("button", { name: "Mwezi uliopita" }),
      ).toBeNull();
      expect(screen.queryByText("Jumla ya wote")).toBeNull();
      shown.unmount();
    }
  });

  it("keeps the pay last read when a refresh fails, with the reason above it", async () => {
    // The shop's internet goes as the page asks again: the totals stay, and the page says why they may be old.
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(new Date("2026-11-25T15:40:00Z"));
    theShopPays({ "2026-11": NOVEMBER });
    render(<PayScreen />);
    await lines();
    answer("GET", PAY_ROUTE, refusal(500, "server_error"));

    await act(() => vi.advanceTimersByTimeAsync(90_000));

    expect(await screen.findByRole("alert")).toBeTruthy();
    expect((await lines())[0]).toBe("Asha | 152,000");
  });
});
