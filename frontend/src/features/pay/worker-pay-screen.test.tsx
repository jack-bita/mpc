// worker-pay-screen.test.tsx — one worker's pay of a month, line by line (WAGE-2): the lines as Jack drew them, a raise,
// today once they tapped Toka, what isn't paid, a month gone by, and what the page says with no worker or no pay.
import { act, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { answer, refusal, sent } from "@/test/fake-server";
import {
  NO_PAY,
  OWNER,
  pay,
  payRoute,
  type WorkerPay,
  workerPay,
  type WorkerPayMonth,
  workerPayMonth,
} from "@/test/pay";
import { render } from "@/test/render";
import { router } from "@/test/router";

import { WorkerPayScreen } from "./worker-pay-screen";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

const ME = "/api/auth/me/";
const JUMA = "019a8600-0000-7000-8000-0000000000aa";

/** Baba is logged in, and the shop pays Juma this. */
function jumaIsPaid(
  worker: Partial<WorkerPay> = {},
  fields: Partial<WorkerPayMonth> = {},
) {
  answer("GET", ME, { status: 200, body: OWNER });
  answer("GET", payRoute(JUMA), {
    status: 200,
    body: workerPayMonth(workerPay({ staff: JUMA, ...worker }), fields),
  });
}

/** The page on Juma's November, unless the address names another month. */
function open(asked: string | null = "2026-11") {
  return render(<WorkerPayScreen staff={JUMA} asked={asked} />);
}

/** Words with the plain space people type for the one Intl writes after "TSh". */
const plain = (part: Element) => (part.textContent ?? "").replace(/ /g, " ");

/** The pay's lines, the total last, each as its parts: "Siku kamili | 14 × 10,000 | 140,000". */
async function lines(): Promise<string[]> {
  const table = await screen.findByRole("table", {
    name: "Malipo, mstari kwa mstari",
  });
  return within(table)
    .getAllByRole("row")
    .map((line) =>
      [...line.children]
        .map(plain)
        .filter((part) => part !== "")
        .join(" | "),
    );
}

/** The months the page asked the server for, in order. */
function monthsAsked(): string[] {
  return sent
    .filter((request) => new URL(request.url).pathname === payRoute(JUMA))
    .map((request) => new URL(request.url).searchParams.get("month") ?? "");
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  // Wednesday 25 November 2026, noon in Arusha.
  vi.setSystemTime(new Date("2026-11-25T09:00:00Z"));
});

afterEach(() => {
  vi.useRealTimers();
});

describe("a worker's pay", () => {
  it("shows Juma's November as Jack drew it", async () => {
    jumaIsPaid({ pay: pay({ waiting: 1 }) });

    open();

    expect(await lines()).toEqual([
      "Siku kamili | 14 × 10,000 | 140,000",
      "Nusu siku | 2 × 5,000 | 10,000",
      "Faini | 2 | − 2,000",
      "Chakula | siku 16 | − 16,000",
      "Jumla ya kumlipa leo | TSh 132,000",
    ]);
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Juma");
    expect(
      screen.getByRole("heading", {
        name: "Novemba 2026 · Hadi jana, Jumanne 24/11",
      }),
    ).toBeTruthy();
    const note = screen.getByText("Siku 1 inasubiri uamuzi");
    expect(plain(note)).toBe("! Siku 1 inasubiri uamuzi");
    expect(monthsAsked()).toEqual(["2026-11"]);
  });

  it("splits a raise into two lines, in the server's order", async () => {
    jumaIsPaid({
      pay: pay({
        lines: [
          { paid_as: "full", days: 8, each: "10000.00", amount: "80000.00" },
          { paid_as: "full", days: 6, each: "12000.00", amount: "72000.00" },
          { paid_as: "half", days: 1, each: "4501.00", amount: "4501.00" },
        ],
        fined_days: 0,
        fines: "0.00",
        meal_days: 0,
        meals: "0.00",
        total: "156501.00",
      }),
      total: "156501.00",
    });

    open();

    // No fine and no meals, so no line of either.
    expect(await lines()).toEqual([
      "Siku kamili | 8 × 10,000 | 80,000",
      "Siku kamili | 6 × 12,000 | 72,000",
      "Nusu siku | 1 × 4,501 | 4,501",
      "Jumla ya kumlipa leo | TSh 156,501",
    ]);
  });

  it("adds today's lines once the worker tapped Toka, its fine and its meals apart", async () => {
    jumaIsPaid({
      today: {
        ...NO_PAY,
        lines: [
          { paid_as: "full", days: 1, each: "10000.00", amount: "10000.00" },
        ],
        fined_days: 1,
        fines: "500.00",
        meal_days: 1,
        meals: "1000.00",
        total: "8500.00",
      },
      total: "140500.00",
    });

    open();

    expect((await lines()).slice(4)).toEqual([
      "Leo: siku kamili | 10,000",
      "Leo: faini | − 500",
      "Leo: chakula | − 1,000",
      "Jumla ya kumlipa leo | TSh 140,500",
    ]);
    // Its lines say it: "Pamoja na leo" is Mishahara's, which has none.
    expect(screen.queryByText("Pamoja na leo")).toBeNull();
  });

  it("shows a half day today, and none of today's fine or meals when there is none", async () => {
    jumaIsPaid({
      pay: NO_PAY,
      today: {
        ...NO_PAY,
        lines: [
          { paid_as: "half", days: 1, each: "5000.00", amount: "5000.00" },
        ],
        total: "5000.00",
      },
      total: "5000.00",
    });

    open();

    expect(await lines()).toEqual([
      "Leo: nusu siku | 5,000",
      "Jumla ya kumlipa leo | TSh 5,000",
    ]);
  });

  it("says what isn't paid: days that wait, days with no daily pay, and today", async () => {
    jumaIsPaid({
      pay: pay({ waiting: 2, no_rate: 1 }),
      today: { ...NO_PAY, waiting: 1 },
      left_on: "2026-11-25",
    });

    open();

    await lines();
    for (const note of [
      "Siku 2 zinasubiri uamuzi",
      "Siku 1 haina malipo kwa siku",
      "Leo inasubiri uamuzi",
      "Aliondoka 25/11/2026",
    ])
      expect(screen.getByText(note)).toBeTruthy();
    expect(screen.queryByText("Leo: siku kamili")).toBeNull();
  });

  it("writes one fine and one day of meals", async () => {
    jumaIsPaid({
      pay: pay({
        lines: [
          { paid_as: "full", days: 1, each: "10000.00", amount: "10000.00" },
        ],
        fined_days: 1,
        fines: "500.00",
        meal_days: 1,
        meals: "1000.00",
        total: "8500.00",
      }),
      total: "8500.00",
    });

    open();

    expect(await lines()).toEqual([
      "Siku kamili | 1 × 10,000 | 10,000",
      "Faini | 1 | − 500",
      "Chakula | siku 1 | − 1,000",
      "Jumla ya kumlipa leo | TSh 8,500",
    ]);
  });

  it("says nothing under the total when all is paid", async () => {
    jumaIsPaid();

    open();

    await lines();
    expect(screen.queryByText(/uamuzi|malipo kwa siku|Aliondoka/)).toBeNull();
  });

  it("shows a total below 0 with its minus", async () => {
    jumaIsPaid({ pay: NO_PAY, total: "-1500.00" });

    open();

    expect(await lines()).toEqual(["Jumla ya kumlipa leo | -TSh 1,500"]);
  });

  it("counts a month gone by to its end, and calls its total the month's", async () => {
    jumaIsPaid({}, { month: "2026-10", counted_to: "2026-10-31" });

    open("2026-10");

    expect((await lines()).at(-1)).toBe("Jumla ya mwezi | TSh 132,000");
    expect(screen.getByRole("heading", { level: 2 }).textContent).toBe(
      "Oktoba 2026",
    );
    expect(monthsAsked()).toEqual(["2026-10"]);
  });

  it("says on the 1st that no day is over yet", async () => {
    jumaIsPaid(
      { pay: NO_PAY, total: "0.00" },
      { month: "2026-12", today: "2026-12-01", counted_to: null },
    );

    open("2026-12");

    expect(await lines()).toEqual(["Jumla ya kumlipa leo | TSh 0"]);
    expect(screen.getByRole("heading", { level: 2 }).textContent).toBe(
      "Desemba 2026 · Bado hakuna siku ya kazi iliyokwisha mwezi huu.",
    );
  });

  it("opens this month when the address names none, or one that is no month", async () => {
    for (const asked of [null, "Novemba", "2026-1", "1999-12"]) {
      sent.length = 0;
      jumaIsPaid();
      const { unmount } = open(asked);
      await lines();
      expect(monthsAsked()).toEqual(["2026-11"]);
      unmount();
    }
  });

  it("says when the shop doesn't pay them by the day, with no lines", async () => {
    jumaIsPaid(
      { display_name: "Baba", pay: NO_PAY, total: "0.00" },
      { paid_by_day: false },
    );

    open();

    expect(
      await screen.findByText("Hana malipo kwa siku katika mwezi huu."),
    ).toBeTruthy();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("names nobody when the address has no worker, and asks nothing", async () => {
    answer("GET", ME, { status: 200, body: OWNER });

    render(<WorkerPayScreen staff={null} asked="2026-11" />);

    expect(
      await screen.findByText("Hakuna mfanyakazi aliyechaguliwa."),
    ).toBeTruthy();
    expect(
      sent.filter((request) => request.url.includes("/staffpay/")),
    ).toEqual([]);
    // Nothing is on its way, so nothing is waited for once the page knows who is here.
    await waitFor(() =>
      expect(screen.queryByText("Subiri kidogo…")).toBeNull(),
    );
  });

  it("shows the server's refusal: no key, or a worker the shop doesn't have", async () => {
    answer("GET", ME, { status: 200, body: OWNER });
    for (const [status, code] of [
      [403, "permission_denied"],
      [404, "not_found"],
    ] as const) {
      answer("GET", payRoute(JUMA), refusal(status, code));
      const { unmount } = open();
      expect(await screen.findByRole("alert")).toBeTruthy();
      expect(screen.queryByRole("table")).toBeNull();
      unmount();
    }
  });

  it("asks this month again by itself, so a Toka shows", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(new Date("2026-11-25T15:40:00Z"));
    jumaIsPaid();
    open();
    await lines();

    await act(() => vi.advanceTimersByTimeAsync(61_000));

    await waitFor(() => expect(monthsAsked()).toHaveLength(2));
  });

  it("goes back to Mishahara on the same month, from a typed address", async () => {
    jumaIsPaid({}, { month: "2026-10" });
    open("2026-10");
    await lines();

    act(() => screen.getByRole("button", { name: "Rudi ulipotoka" }).click());

    expect(router.push).toHaveBeenCalledWith("/pay/?month=2026-10");
  });
});
