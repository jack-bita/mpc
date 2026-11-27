// worker-month-pay.test.tsx — Malipo ya mwezi on a worker's page (WAGE-2): the month's pay line by line, this month's at
// first, moved by ‹ ›, for whoever may see pay alone, and what it says when there is none or it can't be read.
import { act, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { components } from "@/api/schema";
import { answer, refusal, sent } from "@/test/fake-server";
import {
  correction,
  NO_PAY,
  pay,
  payRoute,
  workerPay,
  type WorkerPayMonth,
  workerPayMonth,
} from "@/test/pay";
import { PAY_RATES_ROUTE, payRates } from "@/test/pay-rates";
import { render } from "@/test/render";
import { BABA, MANAGER, STAFF, worker } from "@/test/workers";

import { WorkerScreen } from "./worker-page";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

type Worker = components["schemas"]["Staff"];
type WhoIsHere = components["schemas"]["WhoIsHere"];

const ME = "/api/auth/me/";
const JUMA = worker({ display_name: "Juma" });
const ASHA = worker({ display_name: "Asha" });

/** The pay of Juma's November as Jack drew it, and of his October. */
const NOVEMBER = workerPayMonth(
  workerPay({ staff: JUMA.id, pay: pay({ waiting: 1 }) }),
);
const OCTOBER = workerPayMonth(
  workerPay({
    staff: JUMA.id,
    pay: pay({ fined_days: 0, fines: "0.00", meal_days: 0, meals: "0.00" }),
    total: "150000.00",
  }),
  { month: "2026-10", counted_to: "2026-10-31" },
);

/** The server holds this worker, and their pay of each month; Baba is logged in, unless told otherwise. */
function theServerHas(
  shown: Worker,
  months: Record<string, WorkerPayMonth>,
  who: WhoIsHere = BABA,
): void {
  answer("GET", ME, { status: 200, body: who });
  answer("GET", `${STAFF}${shown.id}/`, { status: 200, body: shown });
  answer("GET", PAY_RATES_ROUTE, { status: 200, body: payRates([], null) });
  answer("GET", payRoute(shown.id), (request) => {
    const month = new URL(request.url).searchParams.get("month") ?? "";
    return months[month]
      ? Response.json(months[month])
      : new Response(null, { status: 404 });
  });
}

/** The card, once its heading shows. */
async function theCard(): Promise<HTMLElement> {
  return screen.findByRole("region", { name: "Malipo ya mwezi" });
}

/** The pay's lines, the total last: "Siku kamili | 14 × 10,000 | 140,000". */
async function lines(card: HTMLElement): Promise<string[]> {
  const table = await within(card).findByRole("table");
  return within(table)
    .getAllByRole("row")
    .map((line) =>
      [...line.children]
        .map((part) => (part.textContent ?? "").replace(/ /g, " "))
        .join(" | "),
    );
}

/** The months of a worker's pay the page asked for, in order. */
function monthsAsked(staff: string): string[] {
  return sent
    .filter((request) => new URL(request.url).pathname === payRoute(staff))
    .map((request) => new URL(request.url).searchParams.get("month") ?? "");
}

const press = (card: HTMLElement, name: string) =>
  fireEvent.click(within(card).getByRole("button", { name }));

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  // Wednesday 25 November 2026, noon in Arusha.
  vi.setSystemTime(new Date("2026-11-25T09:00:00Z"));
});

afterEach(() => {
  vi.useRealTimers();
});

describe("Malipo ya mwezi", () => {
  it("shows this month's pay line by line, as Jack drew it", async () => {
    theServerHas(JUMA, { "2026-11": NOVEMBER });

    render(<WorkerScreen id={JUMA.id} />);
    const card = await theCard();

    expect(await lines(card)).toEqual([
      "Siku kamili | 14 × 10,000 | 140,000",
      "Nusu siku | 2 × 5,000 | 10,000",
      "Faini | 2 | − 2,000",
      "Chakula | siku 16 | − 16,000",
      "Jumla ya kumlipa leo | TSh 132,000",
    ]);
    expect(within(card).getByText("Hadi jana, Jumanne 24/11")).toBeTruthy();
    expect(within(card).getByText("Siku 1 inasubiri uamuzi")).toBeTruthy();
    // The month under the card's own heading, a level down; › stops at this month.
    expect(
      within(card).getByRole("heading", { level: 3, name: "Novemba 2026" }),
    ).toBeTruthy();
    expect(
      within(card)
        .getByRole("button", { name: "Mwezi unaofuata" })
        .getAttribute("aria-disabled"),
    ).toBe("true");
    expect(monthsAsked(JUMA.id)).toEqual(["2026-11"]);
  });

  it("says who approved it, and when, in place of how far it is counted (WAGE-3)", async () => {
    // At 22:30 on the 30th in UTC, 01:30 on 1 December in Arusha. Approving is the worker's own pay page's.
    theServerHas(JUMA, {
      "2026-11": {
        ...NOVEMBER,
        worker: {
          ...NOVEMBER.worker,
          approval: { by: "Baba", at: "2026-11-30T22:30:00Z" },
        },
      },
    });
    render(<WorkerScreen id={JUMA.id} />);
    const card = await theCard();
    expect((await lines(card)).at(-1)).toBe("Jumla ya mwezi | TSh 132,000");
    expect(
      within(card).getByText("Imeidhinishwa na Baba · 01/12/2026 01:30 usiku"),
    ).toBeTruthy();
    expect(within(card).queryByText(/Hadi jana/)).toBeNull();
    expect(
      within(card).queryByRole("button", { name: /Idhinisha/ }),
    ).toBeNull();
  });

  it("takes off what they were given before payday (WAGE-8)", async () => {
    theServerHas(JUMA, {
      "2026-11": workerPayMonth(
        workerPay({
          staff: JUMA.id,
          pay: pay({ advances: "40000.00", total: "92000.00" }),
          total: "92000.00",
        }),
      ),
    });

    render(<WorkerScreen id={JUMA.id} />);

    expect((await lines(await theCard())).slice(-2)).toEqual([
      "Advansi |  | − 40,000",
      "Jumla ya kumlipa leo | TSh 92,000",
    ]);
  });

  it("adds each correction of the month, with its reason, as the worker's pay page does (WAGE-10)", async () => {
    theServerHas(JUMA, {
      "2026-11": workerPayMonth(
        workerPay({
          staff: JUMA.id,
          pay: pay({ corrections: "9000.00", total: "141000.00" }),
          total: "141000.00",
        }),
        { corrections: [correction()] },
      ),
    });

    render(<WorkerScreen id={JUMA.id} />);

    expect((await lines(await theCard())).slice(-2)).toEqual([
      "Marekebisho: Novemba: siku ya 12/11 haikuhesabiwa |  | + 9,000",
      "Jumla ya kumlipa leo | TSh 141,000",
    ]);
  });

  it("shows money given before any working day of the month, and that none has come (WAGE-8)", async () => {
    theServerHas(JUMA, {
      "2026-11": workerPayMonth(
        workerPay({
          staff: JUMA.id,
          pay: { ...NO_PAY, advances: "20000.00", total: "-20000.00" },
          total: "-20000.00",
        }),
        { today: "2026-11-01", counted_to: null, no_day_yet: true },
      ),
    });

    render(<WorkerScreen id={JUMA.id} />);
    const card = await theCard();

    expect((await lines(card))[0]).toBe("Advansi |  | − 20,000");
    expect(
      within(card).getByText("Bado hakuna siku ya kazi iliyokwisha mwezi huu."),
    ).toBeTruthy();
  });

  it("moves to the month before and back, its total then the month's", async () => {
    theServerHas(JUMA, { "2026-11": NOVEMBER, "2026-10": OCTOBER });
    render(<WorkerScreen id={JUMA.id} />);
    const card = await theCard();
    await lines(card);

    press(card, "Mwezi uliopita");

    await within(card).findByText("Jumla ya mwezi");
    expect((await lines(card)).at(-1)).toBe("Jumla ya mwezi | TSh 150,000");
    expect(
      within(card).getByRole("heading", { name: "Oktoba 2026" }),
    ).toBeTruthy();
    expect(within(card).queryByText(/Hadi jana/)).toBeNull();

    press(card, "Mwezi unaofuata");

    await within(card).findByText("Jumla ya kumlipa leo");
    expect(
      within(card).getByRole("heading", { name: "Novemba 2026" }),
    ).toBeTruthy();
  });

  it("waits where it is while another month comes, with the last month's lines gone", async () => {
    // October's totals under November's name, for a moment, could be paid.
    theServerHas(JUMA, { "2026-11": NOVEMBER });
    render(<WorkerScreen id={JUMA.id} />);
    const card = await theCard();
    await lines(card);
    answer("GET", payRoute(JUMA.id), () => new Promise<Response>(() => {}));

    press(card, "Mwezi uliopita");

    expect(
      await within(card).findByRole("heading", { name: "Oktoba 2026" }),
    ).toBeTruthy();
    expect(within(card).getByText("Subiri kidogo…")).toBeTruthy();
    expect(within(card).queryByRole("table")).toBeNull();
  });

  it("shows this month again on another worker's page", async () => {
    // The browser's back and forward move the address from Juma's page to Asha's with the page still on the screen.
    theServerHas(JUMA, { "2026-11": NOVEMBER, "2026-10": OCTOBER });
    theServerHas(ASHA, {
      "2026-11": workerPayMonth(
        workerPay({ staff: ASHA.id, display_name: "Asha", total: "90000.00" }),
      ),
    });
    const { rerender } = render(<WorkerScreen id={JUMA.id} />);
    press(await theCard(), "Mwezi uliopita");
    await screen.findByText("Jumla ya mwezi");

    rerender(<WorkerScreen id={ASHA.id} />);

    await screen.findByText("Jumla ya kumlipa leo");
    expect(monthsAsked(ASHA.id)).toEqual(["2026-11"]);
    expect((await lines(await theCard())).at(-1)).toBe(
      "Jumla ya kumlipa leo | TSh 90,000",
    );
  });

  it("stays on the month it opened on, and lets › reach the next, as the month turns", async () => {
    // Left open on 30 November, unlocked on 1 December: November is being checked before payday.
    vi.setSystemTime(new Date("2026-11-30T09:00:00Z"));
    theServerHas(JUMA, { "2026-11": NOVEMBER });
    render(<WorkerScreen id={JUMA.id} />);
    const card = await theCard();
    await lines(card);

    vi.setSystemTime(new Date("2026-12-01T05:00:00Z"));
    act(() => {
      document.dispatchEvent(new Event("visibilitychange"));
    });

    expect(
      within(card).getByRole("heading", { name: "Novemba 2026" }),
    ).toBeTruthy();
    expect(
      within(card)
        .getByRole("button", { name: "Mwezi unaofuata" })
        .getAttribute("aria-disabled"),
    ).not.toBe("true");
  });

  it("says when the shop doesn't pay them by the day in the month", async () => {
    theServerHas(JUMA, {
      "2026-11": workerPayMonth(workerPay({ staff: JUMA.id }), {
        paid_by_day: false,
      }),
    });

    render(<WorkerScreen id={JUMA.id} />);
    const card = await theCard();

    expect(
      await within(card).findByText("Hana malipo kwa siku katika mwezi huu."),
    ).toBeTruthy();
    expect(within(card).queryByRole("table")).toBeNull();
  });

  it("says only that no day is over yet before the worker's first working day", async () => {
    theServerHas(JUMA, {
      "2026-11": workerPayMonth(workerPay({ staff: JUMA.id }), {
        paid_by_day: false,
        no_day_yet: true,
      }),
    });

    render(<WorkerScreen id={JUMA.id} />);
    const card = await theCard();

    expect(
      await within(card).findByText(
        "Bado hakuna siku ya kazi iliyokwisha mwezi huu.",
      ),
    ).toBeTruthy();
    expect(within(card).queryByText(/Hana malipo|Hadi jana/)).toBeNull();
    expect(within(card).queryByRole("table")).toBeNull();
  });

  it("says why when the pay can't be read, and keeps the other cards", async () => {
    theServerHas(JUMA, {});
    answer("GET", payRoute(JUMA.id), refusal(403, "permission_denied"));

    render(<WorkerScreen id={JUMA.id} />);
    const card = await theCard();

    expect(await within(card).findByRole("alert")).toBeTruthy();
    expect(within(card).queryByRole("table")).toBeNull();
    expect(
      screen.getByRole("region", { name: "Malipo kwa siku" }),
    ).toBeTruthy();
  });

  it("shows no card, and asks nothing, for someone without both keys of pay", async () => {
    theServerHas(JUMA, { "2026-11": NOVEMBER }, MANAGER);

    render(<WorkerScreen id={JUMA.id} />);

    await screen.findByRole("region", { name: "Taarifa zake" });
    expect(
      screen.queryByRole("region", { name: "Malipo ya mwezi" }),
    ).toBeNull();
    expect(monthsAsked(JUMA.id)).toEqual([]);
  });
});
