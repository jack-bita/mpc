// approve-leaver.test.tsx — Idhinisha malipo ya Neema (WAGE-3): one who left, approved alone from their own pay page: who
// is offered it, the sheet as Jack drew it, their Toka on their last evening, what is sent, and the page once approved.
import {
  act,
  fireEvent,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { answer, refusal, sent } from "@/test/fake-server";
import {
  APPROVER,
  nothingStops,
  OWNER,
  pay,
  payRoute,
  type ToApprove,
  workerPay,
  type WorkerPayMonth,
  workerPayMonth,
} from "@/test/pay";
import { render } from "@/test/render";

import { WorkerPayScreen } from "./worker-pay-screen";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

const ME = "/api/auth/me/";
const SLIPS = "/api/v1/staffpay/payslips/";
const NEEMA = "019a8600-0000-7000-8000-0000000000bb";
const OPENER = { name: "Idhinisha malipo ya Neema" };

/** Neema's November on the evening of the 14th, as Jack drew it: 62,000, with Leo. */
function neemasNovember(fields: Partial<WorkerPayMonth> = {}): WorkerPayMonth {
  return workerPayMonth(
    workerPay({
      staff: NEEMA,
      display_name: "Neema",
      left_on: "2026-11-14",
      pay: pay({ total: "53000.00" }),
      today: pay({
        lines: [
          { paid_as: "full", days: 1, each: "10000.00", amount: "10000.00" },
        ],
        fined_days: 0,
        meal_days: 1,
        meals: "1000.00",
        total: "9000.00",
      }),
      total: "62000.00",
    }),
    {
      today: "2026-11-14",
      counted_to: "2026-11-13",
      to_approve: nothingStops(),
      ...fields,
    },
  );
}

/** Approved by Baba at 19:05 on the 14th in Arusha. */
const BY_BABA = { by: "Baba", at: "2026-11-14T16:05:00Z" };
const LINE = "Imeidhinishwa na Baba · 14/11/2026 19:05 usiku";
function approved(): WorkerPayMonth {
  const before = neemasNovember();
  return {
    ...before,
    worker: { ...before.worker, today: null, approval: BY_BABA },
    to_approve: null,
  };
}

/** What the server answers of her November, which a test changes as the server would. */
let november: WorkerPayMonth;

function theShopPays(month: WorkerPayMonth, me = APPROVER) {
  november = month;
  answer("GET", ME, { status: 200, body: me });
  answer("GET", payRoute(NEEMA), () => Response.json(november));
}

function stopped(fields: Partial<ToApprove>): WorkerPayMonth {
  return neemasNovember({ to_approve: nothingStops(fields) });
}

type Sent = { id: string; staff: string; month: string; seen: string };

function bodies(): Promise<Sent[]> {
  return Promise.all(
    sent
      .filter(
        (request) =>
          request.method === "POST" && new URL(request.url).pathname === SLIPS,
      )
      .map((request) => request.clone().json() as Promise<Sent>),
  );
}

async function openSheet() {
  render(<WorkerPayScreen staff={NEEMA} asked="2026-11" />);
  fireEvent.click(await screen.findByRole("button", OPENER));
  return screen.findByRole("dialog");
}

function action(sheet: HTMLElement): HTMLButtonElement {
  return within(sheet).getByRole("button", { name: "Idhinisha" });
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  // Saturday 14 November 2026, 19:05 in Arusha.
  vi.setSystemTime(new Date("2026-11-14T16:05:00Z"));
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("whether it is offered", () => {
  it("is, under the lines of one who left, for whoever may approve it", async () => {
    theShopPays(neemasNovember());
    render(<WorkerPayScreen staff={NEEMA} asked="2026-11" />);
    // The file's first draw, the slowest: given longer, as on a busy laptop it takes more than the usual second.
    expect(
      await screen.findByRole("button", OPENER, { timeout: 5000 }),
    ).toBeTruthy();
  });

  it("isn't without the approval's own key", async () => {
    theShopPays(neemasNovember(), OWNER);
    render(<WorkerPayScreen staff={NEEMA} asked="2026-11" />);
    expect(await screen.findByText("Aliondoka 14/11/2026")).toBeTruthy();
    expect(screen.queryByRole("button", OPENER)).toBeNull();
  });

  it("isn't of one who still works here, nor once it is approved", async () => {
    theShopPays(neemasNovember({ to_approve: null }));
    const { unmount } = render(
      <WorkerPayScreen staff={NEEMA} asked="2026-11" />,
    );
    expect(await screen.findByText("Aliondoka 14/11/2026")).toBeTruthy();
    expect(screen.queryByRole("button", OPENER)).toBeNull();
    unmount();

    theShopPays(approved());
    render(<WorkerPayScreen staff={NEEMA} asked="2026-11" />);
    expect(await screen.findByText(LINE)).toBeTruthy();
    expect(screen.queryByRole("button", OPENER)).toBeNull();
  });
});

describe("the sheet", () => {
  it("says whose, how much, and that it is for good", async () => {
    theShopPays(neemasNovember());
    const sheet = await openSheet();
    expect(
      within(sheet).getByRole("heading", { name: "Idhinisha malipo ya Neema" }),
    ).toBeTruthy();
    expect(sheet.textContent.replace(/ /g, " ")).toContain(
      "Novemba 2026 · Jumla TSh 62,000",
    );
    expect(
      within(sheet).getByText(
        "Baada ya kuidhinisha, malipo yake ya Novemba 2026 hayabadiliki tena.",
      ),
    ).toBeTruthy();
    expect(action(sheet).disabled).toBe(false);
  });

  it("sends her total as it was read, then says who approved it, with the keyboard there", async () => {
    theShopPays(neemasNovember());
    answer("POST", SLIPS, () => {
      november = approved();
      return Response.json(
        {
          id: "x",
          staff: NEEMA,
          month: "2026-11",
          total: "62000.00",
          approved_by: "Baba",
          approved_at: BY_BABA.at,
        },
        { status: 201 },
      );
    });
    const sheet = await openSheet();
    fireEvent.click(action(sheet));
    expect(await screen.findByText(LINE)).toBeTruthy();
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    await waitFor(() => expect(document.activeElement?.textContent).toBe(LINE));
    expect(screen.queryByRole("button", OPENER)).toBeNull();
    expect(await bodies()).toEqual([
      {
        id: expect.stringMatching(/^[0-9a-f-]{36}$/) as string,
        staff: NEEMA,
        month: "2026-11",
        seen: "62000.00",
      },
    ]);
  });

  it("closes with Ghairi, the keyboard back on the button", async () => {
    theShopPays(neemasNovember());
    const sheet = await openSheet();
    fireEvent.click(within(sheet).getByRole("button", { name: "Ghairi" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    await waitFor(() =>
      expect(document.activeElement).toBe(screen.getByRole("button", OPENER)),
    );
    expect(await bodies()).toEqual([]);
  });

  it("waits for her Toka on her last evening", async () => {
    theShopPays(stopped({ still_clocked_in: true }));
    const sheet = await openSheet();
    expect(
      within(sheet).getByText(
        "Bado hajabonyeza Toka leo. Akibonyeza, utaweza kuidhinisha.",
      ),
    ).toBeTruthy();
    expect(action(sheet).disabled).toBe(true);
  });

  it("opens her own earlier month first, and her days that wait", async () => {
    theShopPays(
      stopped({
        earlier: "2026-10",
        waiting: [{ staff: NEEMA, display_name: "Neema", date: "2026-11-12" }],
      }),
    );
    const sheet = await openSheet();
    expect(
      within(sheet)
        .getAllByRole("link")
        .map((link) => [link.textContent, link.getAttribute("href")]),
    ).toEqual([
      ["Oktoba 2026", `/pay/worker?staff=${NEEMA}&month=2026-10`],
      [
        "Neema · Alhamisi 12/11",
        `/attendance-month/worker?staff=${NEEMA}&month=2026-11&day=2026-11-12`,
      ],
    ]);
    expect(action(sheet).disabled).toBe(true);
  });

  it("shows a refusal, and her new total once it has moved", async () => {
    theShopPays(neemasNovember());
    answer("POST", SLIPS, () => {
      november = neemasNovember();
      november = {
        ...november,
        worker: { ...november.worker, total: "60000.00" },
      };
      return Response.json(refusal(400, "pay_run.totals_moved").body, {
        status: 400,
      });
    });
    const sheet = await openSheet();
    fireEvent.click(action(sheet));
    expect(
      await within(sheet).findByText(
        "Hesabu zimebadilika tangu ulipozisoma. Zisome tena, kisha idhinisha.",
      ),
    ).toBeTruthy();
    await waitFor(() =>
      expect(sheet.textContent.replace(/ /g, " ")).toContain(
        "Jumla TSh 60,000",
      ),
    );
  });

  it("closes when the page moves to another month of hers", async () => {
    // Its answer read before, so nothing waits, which would take the sheet away by itself.
    theShopPays(neemasNovember());
    answer("GET", payRoute(NEEMA), (request) =>
      Response.json(
        neemasNovember({
          month: new URL(request.url).searchParams.get("month") ?? "",
        }),
      ),
    );
    const { rerender } = render(
      <WorkerPayScreen staff={NEEMA} asked="2026-10" />,
    );
    await screen.findByRole("button", OPENER);
    rerender(<WorkerPayScreen staff={NEEMA} asked="2026-11" />);
    fireEvent.click(await screen.findByRole("button", OPENER));
    await screen.findByRole("dialog");
    act(() => rerender(<WorkerPayScreen staff={NEEMA} asked="2026-10" />));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });
});

describe("a payslip approved alone", () => {
  it("shows its lines as they were kept, its total final, and no 'up to yesterday'", async () => {
    theShopPays(approved());
    render(<WorkerPayScreen staff={NEEMA} asked="2026-11" />);
    expect(await screen.findByText(LINE)).toBeTruthy();
    expect(
      screen.getByRole("heading", { level: 2, name: "Novemba 2026" }),
    ).toBeTruthy();
    expect(screen.getByText("Jumla ya mwezi")).toBeTruthy();
    expect(screen.queryByText("Jumla ya kumlipa leo")).toBeNull();
    expect(screen.getByText("Aliondoka 14/11/2026")).toBeTruthy();
  });
});
