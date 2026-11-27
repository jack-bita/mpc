// worker-pay-screen.test.tsx — one worker's pay of a month, line by line (WAGE-2): the lines as Jack drew them, a raise,
// what they were given before payday (WAGE-8), today once they tapped Toka, what isn't paid, a month gone by, and what the
// page says with no worker or no pay. And at the foot of a payslip, how it was handed out, Lipa and Batilisha (WAGE-9).
// And the corrections of earlier months, each a line, and who is offered Ongeza marekebisho (WAGE-10).
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
  correction,
  NO_PAY,
  OWNER,
  pay,
  PAYER,
  payment,
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

  it("takes off what they were given before payday, as Jack drew it (WAGE-8)", async () => {
    // Juma's 132,000 less the 20,000 of the 10th and the 20,000 of the 25th, the server's own sums.
    jumaIsPaid({
      pay: pay({ advances: "40000.00", total: "92000.00" }),
      total: "92000.00",
    });

    open();

    expect(await lines()).toEqual([
      "Siku kamili | 14 × 10,000 | 140,000",
      "Nusu siku | 2 × 5,000 | 10,000",
      "Faini | 2 | − 2,000",
      "Chakula | siku 16 | − 16,000",
      "Advansi | − 40,000",
      "Jumla ya kumlipa leo | TSh 92,000",
    ]);
  });

  it("puts it above the total, under today's lines", async () => {
    jumaIsPaid({
      pay: pay({ advances: "40000.00", total: "92000.00" }),
      today: {
        ...NO_PAY,
        lines: [
          { paid_as: "full", days: 1, each: "10000.00", amount: "10000.00" },
        ],
        total: "10000.00",
      },
      total: "102000.00",
    });

    open();

    expect((await lines()).slice(4)).toEqual([
      "Leo: siku kamili | 10,000",
      "Advansi | − 40,000",
      "Jumla ya kumlipa leo | TSh 102,000",
    ]);
  });

  it("shows money given before any working day of the month, and that none has come", async () => {
    // Sunday 1 November: nobody has worked yet, and Juma took 20,000. With the line hidden, the money would be nowhere.
    jumaIsPaid(
      {
        pay: { ...NO_PAY, advances: "20000.00", total: "-20000.00" },
        total: "-20000.00",
      },
      { today: "2026-11-01", counted_to: null, no_day_yet: true },
    );

    open();

    const [line, total, ...more] = await lines();
    expect([line, more]).toEqual(["Advansi | − 20,000", []]);
    expect(total).toMatch(/^Jumla ya kumlipa leo \| [−-]TSh 20,000$/);
    expect(
      screen.getByRole("heading", {
        name: "Novemba 2026 · Bado hakuna siku ya kazi iliyokwisha mwezi huu.",
      }),
    ).toBeTruthy();
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

  it("takes off what an earlier month left owed, under what was given, with its month", async () => {
    jumaIsPaid({
      pay: pay({
        advances: "20000.00",
        carried: "18000.00",
        total: "94000.00",
      }),
      carried_from: "2026-10",
      total: "94000.00",
    });

    open();

    expect((await lines()).slice(-3)).toEqual([
      "Advansi | − 20,000",
      "Deni la Oktoba | − 18,000",
      "Jumla ya kumlipa leo | TSh 94,000",
    ]);
  });

  it.each([
    // A month gone by, still open; of one who left in it, whose debt no pay to come takes; and of one who left in the
    // month after, whose next pay takes it.
    [
      { today: "2026-12-01" },
      {},
      "Analipwa 0. Anadaiwa TSh 18,000, zitakatwa kwenye malipo yake yajayo.",
    ],
    [
      { today: "2026-12-01" },
      { left_on: "2026-11-30" },
      "Analipwa 0. Anadaiwa TSh 18,000.",
    ],
    [
      { today: "2026-12-10" },
      { left_on: "2026-12-01" },
      "Analipwa 0. Anadaiwa TSh 18,000, zitakatwa kwenye malipo yake yajayo.",
    ],
    // Approved, and approved alone this very month: what it was, true however long after it is read.
    [
      { today: "2026-12-01" },
      { approval: { by: "Baba", at: "2026-12-01T16:05:00Z" } },
      "Alilipwa 0. Alibaki anadaiwa TSh 18,000.",
    ],
    [
      {},
      {
        approval: { by: "Baba", at: "2026-11-25T09:00:00Z" },
        left_on: "2026-11-25",
      },
      "Alilipwa 0. Alibaki anadaiwa TSh 18,000.",
    ],
  ])(
    "says what a total below 0 pays and leaves owed: %j %j",
    async (month, worker, said) => {
      jumaIsPaid(
        { pay: pay({ total: "-18000.00" }), total: "-18000.00", ...worker },
        month,
      );

      open();

      await lines();
      expect(
        screen.getByText(
          (_, part) =>
            part?.tagName === "P" &&
            (part.textContent ?? "").replace(/\u00a0/g, " ") === said,
        ),
      ).toBeTruthy();
    },
  );

  it("says nothing of a debt while the month runs, nor of a total of 0 or more", async () => {
    jumaIsPaid({ pay: pay({ total: "-18000.00" }), total: "-18000.00" });
    const { unmount } = open();
    await lines();
    expect(screen.queryByText(/lipwa 0/)).toBeNull();
    unmount();

    jumaIsPaid({ total: "0.00" }, { today: "2026-12-01" });
    open();
    await lines();
    expect(screen.queryByText(/lipwa 0/)).toBeNull();
  });

  it("says who approved the month, and calls its total the month's", async () => {
    jumaIsPaid(
      { approval: { by: "Baba", at: "2026-12-01T16:05:00Z" } },
      { today: "2026-12-01", counted_to: "2026-11-30" },
    );

    open();

    expect((await lines()).at(-1)).toBe("Jumla ya mwezi | TSh 132,000");
    expect(
      screen.getByText("Imeidhinishwa na Baba · 01/12/2026 19:05 usiku"),
    ).toBeTruthy();
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

  it("says only that no day is over yet before the worker's first working day", async () => {
    // Zawadi is hired from the 28th with a rate: "Hana malipo kwa siku" would be untrue (the review).
    jumaIsPaid(
      { display_name: "Zawadi", pay: NO_PAY, total: "0.00" },
      { paid_by_day: false, no_day_yet: true },
    );

    open();

    expect(
      await screen.findByRole("heading", {
        name: "Novemba 2026 · Bado hakuna siku ya kazi iliyokwisha mwezi huu.",
      }),
    ).toBeTruthy();
    expect(screen.queryByText(/Hana malipo|Hadi jana/)).toBeNull();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("opens this month when the address names none, one that is no month, or one to come", async () => {
    for (const asked of [null, "Novemba", "2026-1", "1999-12", "2026-12"]) {
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

describe("corrections (WAGE-10)", () => {
  it("puts each that counts last, with its reason, plus or minus, and none crossed out", async () => {
    // Juma's 132,000, a day of October's left out and 2,000 of fines taken twice: + 11,000, the server's own sums.
    jumaIsPaid(
      {
        pay: pay({ corrections: "11000.00", total: "143000.00" }),
        total: "143000.00",
      },
      {
        corrections: [
          correction({
            amount: "9000.00",
            reason: "Oktoba: siku ya 7/10 haikuhesabiwa",
          }),
          correction({
            id: "019a8800-0000-7000-8000-000000000002",
            amount: "90000.00",
            reason: "Oktoba: kosa",
            voided: {
              by: "Baba",
              at: "2026-12-03T07:20:00Z",
              reason: "Kiasi kimekosewa",
            },
          }),
          correction({
            id: "019a8800-0000-7000-8000-000000000003",
            amount: "2000.00",
            reason: "Oktoba: faini mara mbili",
          }),
        ],
      },
    );

    open();

    expect(await lines()).toEqual([
      "Siku kamili | 14 × 10,000 | 140,000",
      "Nusu siku | 2 × 5,000 | 10,000",
      "Faini | 2 | − 2,000",
      "Chakula | siku 16 | − 16,000",
      "Marekebisho: Oktoba: siku ya 7/10 haikuhesabiwa | + 9,000",
      "Marekebisho: Oktoba: faini mara mbili | + 2,000",
      "Jumla ya kumlipa leo | TSh 143,000",
    ]);
  });

  it("says one taken off with its minus, and a ready reason in words", async () => {
    jumaIsPaid(
      {
        pay: pay({ corrections: "-5000.00", total: "127000.00" }),
        total: "127000.00",
      },
      {
        corrections: [
          correction({ amount: "-5000.00", reason: "paid_too_much" }),
        ],
      },
    );
    open();
    expect((await lines()).at(-2)).toBe(
      "Marekebisho: Alilipwa zaidi | − 5,000",
    );
  });

  it("offers Ongeza marekebisho to whoever approves pay, on a month that takes one", async () => {
    answer("GET", ME, { status: 200, body: APPROVER });
    answer("GET", payRoute(JUMA), {
      status: 200,
      body: workerPayMonth(workerPay({ staff: JUMA })),
    });
    open();
    expect(
      await screen.findByRole("button", { name: "Ongeza marekebisho" }),
    ).toBeTruthy();
  });

  it.each<[string, () => void]>([
    // The two keys of pay alone: seeing the pay is not approving it (Jack: A).
    ["to whoever may not approve pay", () => jumaIsPaid()],
    [
      "on one's own pay",
      () => {
        answer("GET", ME, { status: 200, body: APPROVER });
        answer("GET", payRoute(JUMA), {
          status: 200,
          body: workerPayMonth(workerPay({ staff: JUMA, own: true })),
        });
      },
    ],
    [
      "on a month that takes none",
      () => {
        answer("GET", ME, { status: 200, body: APPROVER });
        answer("GET", payRoute(JUMA), {
          status: 200,
          body: workerPayMonth(workerPay({ staff: JUMA }), {
            no_correction: "pay.day_approved",
          }),
        });
      },
    ],
  ])("offers no Ongeza marekebisho %s", async (_, theServer) => {
    theServer();
    open();
    await lines();
    expect(
      screen.queryByRole("button", { name: "Ongeza marekebisho" }),
    ).toBeNull();
    expect(screen.queryByText(/ameondoka, malipo yake yamefungwa/)).toBeNull();
  });

  it("says nothing of it to whoever may not approve pay", async () => {
    // The sentence explains a button they would never have.
    jumaIsPaid(
      { display_name: "Neema" },
      { no_correction: "correction.left_paid" },
    );
    open();
    await lines();
    expect(screen.queryByText(/ameondoka, malipo yake yamefungwa/)).toBeNull();
  });

  it("says why one who left and was paid takes none (Jack: A)", async () => {
    answer("GET", ME, { status: 200, body: APPROVER });
    answer("GET", payRoute(JUMA), {
      status: 200,
      body: workerPayMonth(workerPay({ staff: JUMA, display_name: "Neema" }), {
        no_correction: "correction.left_paid",
      }),
    });
    open();
    expect(
      await screen.findByText("Neema ameondoka, malipo yake yamefungwa."),
    ).toBeTruthy();
    expect(
      screen.queryByRole("button", { name: "Ongeza marekebisho" }),
    ).toBeNull();
  });
});

describe("the payslip's foot (WAGE-9)", () => {
  const SLIP = "019a8600-0000-7000-8000-0000000005c3";
  const BY_BABA = { by: "Baba", at: "2026-12-01T16:05:00Z" };
  const KEPT = { approval: BY_BABA, payslip: SLIP, total: "132000.00" };

  beforeEach(() => {
    vi.setSystemTime(new Date("2026-12-02T06:00:00Z"));
  });

  function jumasPayslip(
    worker: Partial<WorkerPay>,
    me = PAYER,
    fields: Partial<WorkerPayMonth> = {},
  ) {
    answer("GET", ME, { status: 200, body: me });
    answer("GET", payRoute(JUMA), {
      status: 200,
      body: workerPayMonth(workerPay({ staff: JUMA, ...KEPT, ...worker }), {
        today: "2026-12-02",
        counted_to: "2026-11-30",
        ...fields,
      }),
    });
  }

  function foot(): HTMLElement {
    return screen.getByRole("region", { name: "Malipo yake" });
  }

  it("says who paid it, how and when, with the signature, and offers Batilisha", async () => {
    jumasPayslip({
      payments: [payment({ amount: "132000.00" })],
      to_hand_out: "0.00",
    });
    open();
    expect(
      await screen.findByText(
        "Amelipwa taslimu na Baba · 02/12/2026 08:10 asubuhi",
      ),
    ).toBeTruthy();
    const signature = within(foot()).getByRole("img", {
      name: "Sahihi ya Juma",
    });
    expect(
      new URL(signature.getAttribute("src") ?? "", "http://shop/").pathname,
    ).toBe(
      "/api/v1/control/attachments/019a8700-0000-7000-8000-0000000000a1/file/",
    );
    expect(
      within(foot()).getByRole("button", { name: "Batilisha" }),
    ).toBeTruthy();
    expect(within(foot()).queryByRole("button", { name: "Lipa" })).toBeNull();
  });

  it("says the number of one paid by M-Pesa, with no signature", async () => {
    jumasPayslip({
      payments: [
        payment({
          method: "mobile_money",
          reference: "QK7H2M9XPL",
          signature: null,
        }),
      ],
      to_hand_out: "0.00",
    });
    open();
    expect(
      await screen.findByText("Namba ya muamala: QK7H2M9XPL"),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "Amelipwa kwa M-Pesa na Baba · 02/12/2026 08:10 asubuhi",
      ),
    ).toBeTruthy();
    expect(within(foot()).queryByRole("img")).toBeNull();
  });

  it("keeps one crossed out, struck through, with who and why, and offers Lipa again", async () => {
    const struck = payment({
      voided: {
        by: "Baba",
        at: "2026-12-02T06:00:00Z",
        reason: "Nilibonyeza mfanyakazi mwingine",
      },
    });
    jumasPayslip({ payments: [struck], to_hand_out: "132000.00" });
    open();
    const paid = await screen.findByText(
      "Amelipwa taslimu na Baba · 02/12/2026 08:10 asubuhi",
    );
    expect(paid.tagName).toBe("S");
    expect(
      screen.getByText(
        "Imebatilishwa na Baba · 02/12/2026 09:00 asubuhi: Nilibonyeza mfanyakazi mwingine",
      ),
    ).toBeTruthy();
    // Its signature kept with it, and no Batilisha on what is crossed out already.
    expect(
      within(foot()).getByRole("img", { name: "Sahihi ya Juma" }),
    ).toBeTruthy();
    expect(
      within(foot()).queryByRole("button", { name: "Batilisha" }),
    ).toBeNull();
    expect(within(foot()).getByText("Hajalipwa")).toBeTruthy();
    expect(within(foot()).getByRole("button", { name: "Lipa" })).toBeTruthy();
  });

  it("offers neither Lipa nor Batilisha to whoever may not, nor on one's own", async () => {
    jumasPayslip({ payments: [payment()], to_hand_out: "0.00" }, OWNER);
    open();
    await screen.findByText(
      "Amelipwa taslimu na Baba · 02/12/2026 08:10 asubuhi",
    );
    expect(within(foot()).queryAllByRole("button")).toHaveLength(0);
  });

  it("offers neither on one's own payslip, paid or not", async () => {
    jumasPayslip({ payments: [], to_hand_out: "132000.00", own: true });
    const { unmount } = open();
    expect(await screen.findByText("Hajalipwa")).toBeTruthy();
    expect(within(foot()).queryAllByRole("button")).toHaveLength(0);
    unmount();
    jumasPayslip({ payments: [payment()], to_hand_out: "0.00", own: true });
    open();
    await screen.findByText(
      "Amelipwa taslimu na Baba · 02/12/2026 08:10 asubuhi",
    );
    expect(within(foot()).queryAllByRole("button")).toHaveLength(0);
  });

  it("crosses a payment out with its reason, and lands on Hajalipwa", async () => {
    let worker = workerPay({
      staff: JUMA,
      ...KEPT,
      payments: [payment()],
      to_hand_out: "0.00",
    });
    answer("GET", ME, { status: 200, body: PAYER });
    answer("GET", payRoute(JUMA), () =>
      Response.json(
        workerPayMonth(worker, {
          today: "2026-12-02",
          counted_to: "2026-11-30",
        }),
      ),
    );
    const VOID =
      "/api/v1/staffpay/payslip-payments/019a8700-0000-7000-8000-000000000001/void/";
    answer("POST", VOID, () => {
      const struck = payment({
        voided: {
          by: "Baba",
          at: "2026-12-02T06:00:00Z",
          reason: "Nilibonyeza mfanyakazi mwingine",
        },
      });
      worker = { ...worker, payments: [struck], to_hand_out: "132000.00" };
      return Response.json(struck);
    });
    open();
    fireEvent.click(await screen.findByRole("button", { name: "Batilisha" }));
    const sheet = await screen.findByRole("dialog");
    expect(within(sheet).getByRole("heading").textContent).toBe(
      "Batilisha malipo ya Juma",
    );
    // No reason: said beside the box, nothing sent.
    fireEvent.click(within(sheet).getByRole("button", { name: "Batilisha" }));
    expect(await within(sheet).findByText("Andika sababu.")).toBeTruthy();
    expect(
      sent.filter((request) => new URL(request.url).pathname === VOID),
    ).toHaveLength(0);
    fireEvent.change(within(sheet).getByLabelText("Sababu"), {
      target: { value: "Nilibonyeza mfanyakazi mwingine" },
    });
    fireEvent.click(within(sheet).getByRole("button", { name: "Batilisha" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    const [request] = sent.filter((one) => new URL(one.url).pathname === VOID);
    expect(await request?.clone().json()).toEqual({
      reason: "Nilibonyeza mfanyakazi mwingine",
    });
    await waitFor(() =>
      expect(document.activeElement?.textContent).toBe("Hajalipwa"),
    );
  });

  it("on the demo, offers the ready reason, and says it in words once crossed out", async () => {
    const struck = payment({
      signature: null,
      no_signature: "demo",
      voided: {
        by: "Meneja",
        at: "2026-12-02T06:00:00Z",
        reason: "marked_by_mistake",
      },
    });
    jumasPayslip(
      {
        payments: [
          struck,
          payment({
            id: "019a8700-0000-7000-8000-000000000002",
            signature: null,
            no_signature: "demo",
          }),
        ],
        to_hand_out: "0.00",
      },
      PAYER,
      { void_reasons: ["marked_by_mistake"], keeps_signatures: false },
    );
    open();
    expect(
      await screen.findByText(
        "Imebatilishwa na Meneja · 02/12/2026 09:00 asubuhi: Niliweka kwa makosa",
      ),
    ).toBeTruthy();
    expect(
      within(foot()).getAllByText("Kwenye demo, sahihi haihifadhiwi."),
    ).toHaveLength(2);
    fireEvent.click(within(foot()).getByRole("button", { name: "Batilisha" }));
    const sheet = await screen.findByRole("dialog");
    expect(
      within(sheet).getByRole("radio", { name: "Niliweka kwa makosa" }),
    ).toBeTruthy();
  });
});
