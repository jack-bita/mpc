// approve-month.test.tsx — Idhinisha on Mishahara (WAGE-3): who is offered it, the sheet as Jack drew it, what stops it,
// what it warns of, what is sent, and the page once the month is approved.
import { QueryClient, useQueryClient } from "@tanstack/react-query";
import {
  act,
  fireEvent,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ADVANCES } from "@/features/advances/advances";
import {
  ATTENDANCE_MONTHS,
  monthOf,
} from "@/features/attendance/attendance-month";
import { WORKER_MONTHS } from "@/features/attendance/worker-month";
import { MEAL_MONEY } from "@/features/meals/meal-money";
import { answer, refusal, sent } from "@/test/fake-server";
import {
  APPROVER,
  nothingStops,
  OWNER,
  PAY_ROUTE,
  type PayMonth,
  payMonth,
  workerPay,
} from "@/test/pay";
import { render } from "@/test/render";

import { mayApprovePay, PAY } from "./pay";
import { PayScreen } from "./pay-screen";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

const ME = "/api/auth/me/";
const RUNS = "/api/v1/staffpay/pay-runs/";
const ASHA = workerPay({ display_name: "Asha", total: "152000.00" });
const BARAKA = workerPay({ display_name: "Baraka", total: "148000.00" });
const JUMA = workerPay({ display_name: "Juma", total: "132000.00" });

/** November, over and open, as Jack drew it (25 Nov 2026): 432,000 for three. */
const OVER = payMonth([ASHA, BARAKA, JUMA], {
  today: "2026-12-01",
  counted_to: "2026-11-30",
  total: "432000.00",
  to_approve: nothingStops(),
});

/** Approved by Baba at 19:05 on 1 December in Arusha. */
const BY_BABA = { by: "Baba", at: "2026-12-01T16:05:00Z" };
const APPROVED: PayMonth = {
  ...OVER,
  workers: OVER.workers.map((worker) => ({ ...worker, approval: BY_BABA })),
  approval: BY_BABA,
  to_approve: null,
};

/** The month the server answers, which a test changes as the server would. */
let november: PayMonth;

function theShopPays(month: PayMonth, me = APPROVER) {
  november = month;
  answer("GET", ME, { status: 200, body: me });
  answer("GET", PAY_ROUTE, () => Response.json(november));
}

type Sent = { id: string; month: string; seen: { total: string }[] };

/** What was sent to approve, in order. */
function bodies(): Promise<Sent[]> {
  return Promise.all(
    sent
      .filter(
        (request) =>
          request.method === "POST" && new URL(request.url).pathname === RUNS,
      )
      .map((request) => request.clone().json() as Promise<Sent>),
  );
}

const OPENER = { name: "Idhinisha Novemba 2026" };

/** What the sheet says once a total is no longer the one it opened with, in the server's own sentence. */
const MOVED =
  "Hesabu zimebadilika tangu ulipozisoma. Zisome tena, kisha idhinisha.";

/** A part's words, with the plain space people type for the one Intl writes after "TSh". */
function wordsOf(part: HTMLElement): string {
  return part.textContent.replace(/\u00a0/g, " ");
}

/** Reads the pay again behind the open sheet, as a save on another page of the app does. */
function ReadAgain() {
  const store = useQueryClient();
  return (
    <button
      type="button"
      onClick={() => void store.invalidateQueries({ queryKey: PAY })}
    >
      Soma tena
    </button>
  );
}

/** The page with its sheet open. */
async function openSheet() {
  const { container, ...rest } = render(
    <>
      <PayScreen />
      <ReadAgain />
    </>,
  );
  fireEvent.click(await screen.findByRole("button", OPENER));
  return { sheet: await screen.findByRole("dialog"), container, ...rest };
}

function action(sheet: HTMLElement): HTMLButtonElement {
  return within(sheet).getByRole("button", { name: "Idhinisha" });
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  // Tuesday 1 December 2026, 19:05 in Arusha.
  vi.setSystemTime(new Date("2026-12-01T16:05:00Z"));
  window.history.replaceState(null, "", "/pay/?month=2026-11");
});

afterEach(() => {
  vi.useRealTimers();
  // What was spied on, and a network taken away, which the store of server answers waits for until it hears it is back.
  vi.restoreAllMocks();
  act(() => {
    window.dispatchEvent(new Event("online"));
  });
});

describe("whether Idhinisha is offered", () => {
  it("is, at the foot of a month that is over, for whoever may approve it", async () => {
    theShopPays(OVER);
    render(<PayScreen />);
    // The file's first draw, the slowest: given longer, as on a busy laptop it takes more than the usual second.
    expect(
      await screen.findByRole("button", OPENER, { timeout: 5000 }),
    ).toBeTruthy();
  });

  it("isn't without the approval's own key, though they may see the pay", async () => {
    theShopPays(OVER, OWNER);
    render(<PayScreen />);
    expect(await screen.findByText("Jumla ya wote")).toBeTruthy();
    expect(screen.queryByRole("button", OPENER)).toBeNull();
  });

  it("isn't while the month runs, nor once it is approved", async () => {
    theShopPays({ ...OVER, to_approve: null });
    const { unmount } = render(<PayScreen />);
    expect(await screen.findByText("Jumla ya wote")).toBeTruthy();
    expect(screen.queryByRole("button", OPENER)).toBeNull();
    unmount();

    theShopPays(APPROVED);
    render(<PayScreen />);
    expect(
      await screen.findByText("Imeidhinishwa na Baba · 01/12/2026 19:05 usiku"),
    ).toBeTruthy();
    expect(screen.queryByRole("button", OPENER)).toBeNull();
  });
});

describe("who may approve", () => {
  it.each([
    [["pay.approve", "settings.manage", "staff.manage"], true],
    [["settings.manage", "staff.manage"], false],
    [["pay.approve", "staff.manage"], false],
    [["pay.approve", "settings.manage"], false],
  ])("holds all three keys on the whole shop: %j is %s", (held, may) => {
    const me = { ...OWNER, permissions: { whole_shop: held, sides: [] } };
    expect(mayApprovePay(me)).toBe(may);
  });
});

describe("the sheet", () => {
  it("says who, how much, and that it is for good, as Jack drew it", async () => {
    theShopPays(OVER);
    const { sheet } = await openSheet();
    expect(
      within(sheet).getByRole("heading", { name: "Idhinisha Novemba 2026" }),
    ).toBeTruthy();
    expect(sheet.textContent.replace(/\u00a0/g, " ")).toContain(
      "Watu 3 · Jumla TSh 432,000",
    );
    expect(
      within(sheet).getByText(
        "Baada ya kuidhinisha, Novemba 2026 haibadiliki tena.",
      ),
    ).toBeTruthy();
    // Nothing stops it, so nothing is listed.
    expect(within(sheet).queryByRole("list")).toBeNull();
    expect(within(sheet).queryByText(/kwanza/)).toBeNull();
    expect(action(sheet).disabled).toBe(false);
  });

  it("sends each total as it was read, then says who approved it, with the keyboard there", async () => {
    theShopPays(OVER);
    answer("POST", RUNS, () => {
      november = APPROVED;
      return Response.json(
        {
          id: "x",
          month: "2026-11",
          approved_by: "Baba",
          approved_at: BY_BABA.at,
        },
        { status: 201 },
      );
    });
    const { sheet } = await openSheet();
    fireEvent.click(action(sheet));

    const line = await screen.findByText(
      "Imeidhinishwa na Baba · 01/12/2026 19:05 usiku",
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    await waitFor(() =>
      expect(document.activeElement).toBe(line.parentElement),
    );
    expect(screen.queryByRole("button", OPENER)).toBeNull();
    expect(await bodies()).toEqual([
      {
        id: expect.stringMatching(/^[0-9a-f-]{36}$/) as string,
        month: "2026-11",
        seen: [
          { staff: ASHA.staff, total: "152000.00" },
          { staff: BARAKA.staff, total: "148000.00" },
          { staff: JUMA.staff, total: "132000.00" },
        ],
      },
    ]);
  });

  it("asks every page it locks again", async () => {
    theShopPays(OVER);
    answer("POST", RUNS, {
      status: 201,
      body: {
        id: "x",
        month: "2026-11",
        approved_by: "Baba",
        approved_at: BY_BABA.at,
      },
    });
    const { sheet } = await openSheet();
    const asked = vi.spyOn(QueryClient.prototype, "invalidateQueries");
    fireEvent.click(action(sheet));
    await waitFor(() => expect(asked).toHaveBeenCalled());
    expect(asked.mock.calls.map(([filters]) => filters?.queryKey)).toEqual([
      PAY,
      ATTENDANCE_MONTHS,
      WORKER_MONTHS,
      MEAL_MONEY,
      ADVANCES,
    ]);
  });

  it("waits for the month to be read again before it closes", async () => {
    // So it never closes onto a month that still looks open, its button there to tap again.
    theShopPays(OVER);
    let answerTheMonth: (() => void) | undefined;
    answer("POST", RUNS, () => {
      november = APPROVED;
      answer(
        "GET",
        PAY_ROUTE,
        () =>
          new Promise<Response>((resolve) => {
            answerTheMonth = () => resolve(Response.json(november));
          }),
      );
      return Response.json(
        {
          id: "x",
          month: "2026-11",
          approved_by: "Baba",
          approved_at: BY_BABA.at,
        },
        { status: 201 },
      );
    });
    const { sheet } = await openSheet();
    fireEvent.click(action(sheet));
    await waitFor(() => expect(answerTheMonth).toBeDefined());
    expect(screen.getByRole("dialog")).toBeTruthy();
    expect(action(sheet).disabled).toBe(true);
    act(() => answerTheMonth?.());
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("moves the page to an earlier month to approve first, and goes with the month it was of", async () => {
    // October's page, with November's sheet still over it, would approve a month nobody is looking at.
    theShopPays(OVER);
    const october = { ...OVER, month: "2026-10", counted_to: "2026-10-31" };
    answer("GET", PAY_ROUTE, (request) =>
      Response.json(
        new URL(request.url).searchParams.get("month") === "2026-10"
          ? october
          : { ...OVER, to_approve: nothingStops({ earlier: "2026-10" }) },
      ),
    );
    // October read before, so its answer is there at once: nothing waits, which would take November's sheet away by itself.
    render(<PayScreen />);
    await screen.findByRole("button", OPENER);
    fireEvent.click(screen.getByRole("button", { name: "Mwezi uliopita" }));
    await screen.findByRole("button", { name: "Idhinisha Oktoba 2026" });
    fireEvent.click(screen.getByRole("button", { name: "Mwezi unaofuata" }));
    fireEvent.click(await screen.findByRole("button", OPENER));
    const sheet = await screen.findByRole("dialog");
    expect(within(sheet).getByText("Idhinisha kwanza:")).toBeTruthy();
    fireEvent.click(within(sheet).getByRole("button", { name: "Oktoba 2026" }));
    expect(
      await screen.findByRole("button", { name: "Idhinisha Oktoba 2026" }),
    ).toBeTruthy();
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(window.location.search).toBe("?month=2026-10");
    expect(await bodies()).toEqual([]);
    await waitFor(() =>
      expect(document.activeElement).toBe(
        screen.getByRole("heading", { name: "Mishahara" }),
      ),
    );
  });

  it("makes a request of its own each time it opens", async () => {
    // Closed and opened again, it is another wish to approve: a refusal of the first says nothing of the second.
    theShopPays(OVER);
    answer("POST", RUNS, refusal(400, "pay_run.days_waiting"));
    const { sheet } = await openSheet();
    fireEvent.click(action(sheet));
    await within(sheet).findByRole("alert");
    fireEvent.click(within(sheet).getByRole("button", { name: "Ghairi" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    fireEvent.click(screen.getByRole("button", OPENER));
    const again = await screen.findByRole("dialog");
    expect(within(again).queryByRole("alert")).toBeNull();
    fireEvent.click(action(again));
    await within(again).findByRole("alert");
    const [first, second] = await bodies();
    expect(second?.id).not.toBe(first?.id);
  });

  it("closes with Ghairi, sending nothing, the keyboard back on the button", async () => {
    theShopPays(OVER);
    const { sheet } = await openSheet();
    fireEvent.click(within(sheet).getByRole("button", { name: "Ghairi" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    await waitFor(() =>
      expect(document.activeElement).toBe(screen.getByRole("button", OPENER)),
    );
    expect(await bodies()).toEqual([]);
  });

  it("is held offline", async () => {
    theShopPays(OVER);
    const { sheet } = await openSheet();
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    act(() => {
      window.dispatchEvent(new Event("offline"));
    });
    await waitFor(() => expect(action(sheet).disabled).toBe(true));
  });
});

describe("what stops it", () => {
  it("names each, with where it is mended, and holds the button", async () => {
    theShopPays({
      ...OVER,
      to_approve: nothingStops({
        waiting: [
          { staff: JUMA.staff, display_name: "Juma", date: "2026-11-12" },
          { staff: ASHA.staff, display_name: "Asha", date: "2026-11-18" },
        ],
        no_rate: [
          { staff: BARAKA.staff, display_name: "Baraka", date: "2026-11-02" },
        ],
      }),
    });
    const { sheet } = await openSheet();
    expect(action(sheet).disabled).toBe(true);
    expect(within(sheet).queryByText(/haibadiliki tena/)).toBeNull();
    const links = within(sheet)
      .getAllByRole("link")
      .map((link) => [link.textContent, link.getAttribute("href")]);
    expect(links).toEqual([
      [
        "Juma · Alhamisi 12/11",
        `/attendance-month/worker?staff=${JUMA.staff}&month=${monthOf("2026-11-12")}&day=2026-11-12`,
      ],
      [
        "Asha · Jumatano 18/11",
        `/attendance-month/worker?staff=${ASHA.staff}&month=2026-11&day=2026-11-18`,
      ],
      ["Baraka · Jumatatu 02/11", `/workers/view?id=${BARAKA.staff}`],
    ]);
    expect(
      within(sheet).getByRole("list", { name: "Amua siku hizi kwanza:" }),
    ).toBeTruthy();
    expect(
      within(sheet).getByRole("list", {
        name: "Siku hii haina malipo kwa siku:",
      }),
    ).toBeTruthy();
  });

  it.each([
    ["earlier", { earlier: "2026-10" }],
    [
      "waiting",
      {
        waiting: [
          { staff: JUMA.staff, display_name: "Juma", date: "2026-11-12" },
        ],
      },
    ],
    [
      "no_rate",
      {
        no_rate: [
          { staff: JUMA.staff, display_name: "Juma", date: "2026-11-12" },
        ],
      },
    ],
    ["still_clocked_in", { still_clocked_in: true }],
  ])("is held by %s alone", async (_name, stops) => {
    theShopPays({ ...OVER, to_approve: nothingStops(stops) });
    const { sheet } = await openSheet();
    expect(action(sheet).disabled).toBe(true);
  });

  it("warns of a quiet laptop and of who came with no daily pay, and stops nothing", async () => {
    theShopPays({
      ...OVER,
      to_approve: nothingStops({
        quiet_laptops: [
          {
            name: "Laptop ya Vyakula",
            // 22:30 on 28 November in UTC is the 29th in Arusha.
            last_synced_at: "2026-11-28T22:30:00Z",
          },
          { name: "Simu ya Baba", last_synced_at: null },
        ],
        came_unpaid: ["Zawadi"],
      }),
    });
    const { sheet } = await openSheet();
    for (const said of [
      "Laptop ya Vyakula haijatuma tangu 29/11/2026",
      "Simu ya Baba haijawahi kutuma",
      "Zawadi alikuja kazini, lakini hana malipo kwa siku",
    ])
      expect(sheet.textContent).toContain(said);
    expect(action(sheet).disabled).toBe(false);
  });
});

describe("a refusal", () => {
  it("shows in the sheet once a total has moved, and what is approved is only what is read again", async () => {
    theShopPays(OVER);
    let tries = 0;
    answer("POST", RUNS, () => {
      tries += 1;
      if (tries > 1) {
        november = APPROVED;
        return Response.json(
          {
            id: "x",
            month: "2026-11",
            approved_by: "Baba",
            approved_at: BY_BABA.at,
          },
          { status: 201 },
        );
      }
      november = {
        ...OVER,
        workers: [{ ...ASHA, total: "142000.00" }, BARAKA, JUMA],
        total: "422000.00",
      };
      return Response.json(refusal(400, "pay_run.totals_moved").body, {
        status: 400,
      });
    });
    const { sheet } = await openSheet();
    fireEvent.click(action(sheet));
    expect(await within(sheet).findByText(MOVED)).toBeTruthy();
    // The page behind has the new totals; the sheet keeps what was read, and takes no second tap. Said once.
    await screen.findByText(/422,000/);
    await waitFor(() => expect(action(sheet).disabled).toBe(true));
    expect(wordsOf(sheet)).toContain("Watu 3 · Jumla TSh 432,000");
    expect(within(sheet).getAllByText(MOVED)).toHaveLength(1);
    fireEvent.click(within(sheet).getByRole("button", { name: "Ghairi" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    // Read on the page, and approved as it was read: another wish, with a request of its own.
    fireEvent.click(screen.getByRole("button", OPENER));
    const again = await screen.findByRole("dialog");
    expect(wordsOf(again)).toContain("Watu 3 · Jumla TSh 422,000");
    fireEvent.click(action(again));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    const [first, second] = await bodies();
    expect(second?.id).not.toBe(first?.id);
    expect(second?.seen.map(({ total }) => total)).toEqual([
      "142000.00",
      "148000.00",
      "132000.00",
    ]);
  });

  it("holds the button when a total moves under the open sheet, with nothing sent (WAGE-3's review)", async () => {
    // Juma's day is decided on another phone, and the page behind is read again: two totals that cancel each other out
    // leave the whole as it was, and have moved all the same.
    theShopPays(OVER);
    const { sheet } = await openSheet();
    expect(action(sheet).disabled).toBe(false);
    november = {
      ...OVER,
      workers: [
        { ...ASHA, total: "142000.00" },
        BARAKA,
        { ...JUMA, total: "142000.00" },
      ],
    };
    fireEvent.click(screen.getByText("Soma tena"));
    expect(await within(sheet).findByText(MOVED)).toBeTruthy();
    expect(action(sheet).disabled).toBe(true);
    // It moves back: what was read is true again.
    november = OVER;
    fireEvent.click(screen.getByText("Soma tena"));
    await waitFor(() => expect(action(sheet).disabled).toBe(false));
    expect(within(sheet).queryByText(MOVED)).toBeNull();
    expect(await bodies()).toEqual([]);
  });

  it("asks the month again when no answer came, as it may have been approved all the same", async () => {
    theShopPays(OVER);
    answer("POST", RUNS, () => {
      november = APPROVED;
      throw new TypeError("Failed to fetch");
    });
    const { sheet } = await openSheet();
    fireEvent.click(action(sheet));
    expect(
      await screen.findByText("Imeidhinishwa na Baba · 01/12/2026 19:05 usiku"),
    ).toBeTruthy();
    // Still open, with why: sent again, the server answers the approval it made.
    expect(screen.getByRole("dialog")).toBeTruthy();
    expect(action(sheet).disabled).toBe(false);
    // Closed with Ghairi, its button gone, the keyboard is on the line.
    fireEvent.click(within(sheet).getByRole("button", { name: "Ghairi" }));
    await waitFor(() =>
      expect(document.activeElement?.textContent).toBe(
        "Imeidhinishwa na Baba · 01/12/2026 19:05 usiku",
      ),
    );
  });
});

describe("an approved month", () => {
  it("shows the payslips as they were kept, and who approved them once", async () => {
    theShopPays(APPROVED);
    render(<PayScreen />);
    const list = await screen.findByRole("list", {
      name: "Malipo ya kila mfanyakazi",
    });
    expect(
      within(list)
        .getAllByRole("listitem")
        .map((line) => line.textContent),
    ).toEqual(["Asha152,000", "Baraka148,000", "Juma132,000"]);
    expect(screen.getAllByText(/Imeidhinishwa/)).toHaveLength(1);
  });

  it("says under their name that one who left was approved alone, while the month is open", async () => {
    theShopPays({
      ...OVER,
      workers: [
        ASHA,
        workerPay({
          display_name: "Neema",
          left_on: "2026-11-14",
          total: "62000.00",
          // 22:30 on the 14th in UTC is the 15th in Arusha.
          approval: { by: "Baba", at: "2026-11-14T22:30:00Z" },
        }),
      ],
    });
    render(<PayScreen />);
    const list = await screen.findByRole("list", {
      name: "Malipo ya kila mfanyakazi",
    });
    const lines = within(list)
      .getAllByRole("listitem")
      .map((line) => [...line.querySelectorAll("p")].map((p) => p.textContent));
    expect(lines).toEqual([
      ["Asha", "152,000"],
      ["Neema", "62,000", "Aliondoka 14/11/2026", "Imeidhinishwa 15/11/2026"],
    ]);
  });
});
