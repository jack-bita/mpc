// printed-payslips.test.tsx — the payslips printed on A4 (WAGE-5): each line as its payslip kept it, worded as the pay
// page words them, each advance with its day, as Jack drew it (28 Nov 2026); every payslip of a month one page each, or
// one worker's alone, a leaver approved alone among them; a debt, a correction, one not paid yet; and nothing of a month
// still open. Fake data only: every name, amount and id is made up (rule 10).
import { fireEvent, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { answer } from "@/test/fake-server";
import {
  OWNER,
  PAY_ROUTE,
  payment,
  type PayMonth,
  payMonth,
  type WorkerPay,
  workerPay,
} from "@/test/pay";
import { render } from "@/test/render";
import { router } from "@/test/router";

import { PrintedPayslipsScreen } from "./printed-payslips";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

const ME = "/api/auth/me/";
/** The minus the books write before an amount taken off ("− 1,000"), not the hyphen a keyboard types. */
const MINUS = "−";

type KeptLine = WorkerPay["kept_lines"][number];

/** A kept line of a payslip: what its kind holds, the rest empty, as the server answers it. */
function kept(
  kind: KeptLine["kind"],
  amount: string,
  fields: Partial<KeptLine> = {},
): KeptLine {
  return {
    kind,
    days: null,
    each: null,
    date: null,
    amount,
    note: "",
    ...fields,
  };
}

/** Approved by Baba at 09:00 on 1 December in Arusha. */
const APPROVED = { by: "Baba", at: "2026-12-01T06:00:00Z" };

/** Asha's November as Jack drew it: two advances, each its own line, paid in cash and signed. */
const ASHA = workerPay({
  staff: "019a8600-0000-7000-8000-0000000000a5",
  display_name: "Asha",
  total: "152000.00",
  payslip: "019a8900-0000-7000-8000-000000000001",
  approval: APPROVED,
  payments: [payment()],
  kept_lines: [
    kept("full", "180000.00", { days: 20, each: "9000.00" }),
    kept("half", "9000.00", { days: 2, each: "4500.00" }),
    kept("fines", "-1000.00", { days: 2 }),
    kept("meals", "-16000.00", { days: 22 }),
    kept("advance", "-10000.00", { date: "2026-11-05" }),
    kept("advance", "-10000.00", { date: "2026-11-18" }),
  ],
});

/** Neema's: November's days, October's debt, and a correction of October's: she owes. Not paid, as she is handed nothing. */
const NEEMA = workerPay({
  staff: "019a8600-0000-7000-8000-0000000000e1",
  display_name: "Neema",
  total: "-18000.00",
  payslip: "019a8900-0000-7000-8000-000000000004",
  approval: APPROVED,
  kept_lines: [
    kept("full", "24000.00", { days: 3, each: "8000.00" }),
    kept("meals", "-4000.00", { days: 3 }),
    kept("advance", "-20000.00", { date: "2026-11-10" }),
    kept("carried", "-27000.00", { date: "2026-10-01" }),
    kept("correction", "9000.00", {
      note: "Oktoba: siku ya 7/10 haikuhesabiwa",
    }),
  ],
});

/** Asha's November while it is still open: a draft, which no payslip keeps. */
const ASHA_DRAFT = workerPay({
  staff: "019a8600-0000-7000-8000-0000000000a6",
  display_name: "Asha",
  total: "152000.00",
});

const NOVEMBER = payMonth([ASHA, NEEMA], {
  total: "152000.00",
  approval: APPROVED,
  still_to_pay: "0.00",
});

function theShopPays(month: PayMonth) {
  answer("GET", ME, { status: 200, body: OWNER });
  answer("GET", PAY_ROUTE, { status: 200, body: month });
}

/** A part's words, with the plain space people type for the ones Intl writes after "TSh". */
function wordsOf(part: Element | null): string {
  return (part?.textContent ?? "").replace(/[  ]/g, " ").trim();
}

/** The payslips, each as its page: its worker's name, its lines' cells, its total and its last lines. */
async function payslips(): Promise<Element[]> {
  await screen.findAllByRole("table");
  return [...document.querySelectorAll("section")];
}

function linesOf(slip: Element): string[][] {
  return within(slip as HTMLElement)
    .getAllByRole("row")
    .map((row) => [...row.querySelectorAll("th, td")].map(wordsOf));
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  // Friday 4 December 2026, in Arusha.
  vi.setSystemTime(new Date("2026-12-04T09:00:00Z"));
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("the printed payslips", () => {
  it("prints Asha's as Jack drew it, each advance with its day", async () => {
    theShopPays(
      payMonth([ASHA], {
        total: "152000.00",
        approval: APPROVED,
        still_to_pay: "0.00",
      }),
    );
    render(<PrintedPayslipsScreen asked="2026-11" staff={null} />);

    const [slip] = await payslips();
    expect(slip).toBeDefined();
    expect(linesOf(slip as Element)).toEqual([
      ["Siku kamili", "20 × 9,000", "180,000"],
      ["Nusu siku", "2 × 4,500", "9,000"],
      ["Faini", "siku 2", `${MINUS} 1,000`],
      ["Chakula", "siku 22", `${MINUS} 16,000`],
      ["Advansi ya 05/11/2026", "", `${MINUS} 10,000`],
      ["Advansi ya 18/11/2026", "", `${MINUS} 10,000`],
      ["Jumla ya mwezi", "TSh 152,000"],
    ]);
    const page = within(slip as HTMLElement);
    expect(page.getByRole("heading", { level: 2 }).textContent).toBe(
      "Hati ya malipo · Novemba 2026",
    );
    expect(page.getByText("Asha")).toBeDefined();
    expect(
      page.getByText("Imeidhinishwa na Baba · 01/12/2026 09:00 asubuhi"),
    ).toBeDefined();
    expect(
      page.getByText("Amelipwa taslimu na Baba · 02/12/2026 08:10 asubuhi"),
    ).toBeDefined();
    // Fetched at once, never lazily as it nears the screen: Chapisha waits for it (WAGE-5's review).
    expect(
      page.getByRole("img", { name: "Sahihi ya Asha" }).getAttribute("loading"),
    ).toBe("eager");
  });

  it("prints every payslip of the month, each on a page of its own", async () => {
    theShopPays(NOVEMBER);
    render(<PrintedPayslipsScreen asked="2026-11" staff={null} />);

    const slips = await payslips();
    expect(
      slips.map((slip) => slip.querySelector("header + p")?.textContent),
    ).toEqual(["Asha", "Neema"]);
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(
      "Hati za malipo",
    );
  });

  it("says a debt, a correction with its reason, and what was owed, never Hajalipwa", async () => {
    theShopPays(NOVEMBER);
    render(<PrintedPayslipsScreen asked="2026-11" staff={NEEMA.staff} />);

    const [slip] = await payslips();
    expect(linesOf(slip as Element)).toEqual([
      ["Siku kamili", "3 × 8,000", "24,000"],
      ["Chakula", "siku 3", `${MINUS} 4,000`],
      ["Advansi ya 10/11/2026", "", `${MINUS} 20,000`],
      ["Deni la Oktoba", "", `${MINUS} 27,000`],
      ["Marekebisho: Oktoba: siku ya 7/10 haikuhesabiwa", "", "+ 9,000"],
      // The total as the pay page writes one below 0, by the shared formatter (formatMoney).
      ["Jumla ya mwezi", "-TSh 18,000"],
    ]);
    const page = within(slip as HTMLElement);
    expect(wordsOf(page.getByText(/^Alilipwa 0/))).toBe(
      "Alilipwa 0. Alibaki anadaiwa TSh 18,000.",
    );
    expect(page.queryByText("Hajalipwa")).toBeNull();
  });

  it("prints one worker's alone, from their pay page, and its arrow goes back there", async () => {
    theShopPays(NOVEMBER);
    render(<PrintedPayslipsScreen asked="2026-11" staff={ASHA.staff} />);

    const slips = await payslips();
    expect(slips).toHaveLength(1);
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(
      "Hati ya malipo",
    );
    fireEvent.click(screen.getByRole("button", { name: "Rudi ulipotoka" }));
    expect(router.push).toHaveBeenCalledWith(
      `/pay/worker/?staff=${ASHA.staff}&month=2026-11`,
    );
  });

  it("prints a leaver approved alone, before the month is", async () => {
    // Neema left on 14 November, and was approved alone that evening; the month runs on for the others.
    const alone = {
      ...NEEMA,
      left_on: "2026-11-14",
      approval: { by: "Baba", at: "2026-11-14T16:00:00Z" },
    };
    theShopPays(payMonth([ASHA_DRAFT, alone], { total: "0.00" }));
    render(<PrintedPayslipsScreen asked="2026-11" staff={NEEMA.staff} />);

    const [slip] = await payslips();
    const page = within(slip as HTMLElement);
    expect(page.getByText("Aliondoka 14/11/2026")).toBeDefined();
    expect(
      page.getByText("Imeidhinishwa na Baba · 14/11/2026 19:00 usiku"),
    ).toBeDefined();
  });

  it("prints nobody's from Mishahara while the month is open, a leaver's kept payslip neither", async () => {
    // Everyone's payslips are the month's, once it is approved; a leaver approved alone prints from her own page.
    const alone = {
      ...NEEMA,
      left_on: "2026-11-14",
      approval: { by: "Baba", at: "2026-11-14T16:00:00Z" },
    };
    theShopPays(payMonth([ASHA_DRAFT, alone], { total: "0.00" }));
    render(<PrintedPayslipsScreen asked="2026-11" staff={null} />);

    expect(
      await screen.findByText(
        "Hati ya malipo inapatikana malipo yakishaidhinishwa.",
      ),
    ).toBeDefined();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("says Hajalipwa of one not paid yet", async () => {
    const unpaid = { ...ASHA, payments: [], to_hand_out: "152000.00" };
    theShopPays(
      payMonth([unpaid], {
        total: "152000.00",
        approval: APPROVED,
        still_to_pay: "152000.00",
      }),
    );
    render(<PrintedPayslipsScreen asked="2026-11" staff={null} />);

    const [slip] = await payslips();
    expect(within(slip as HTMLElement).getByText("Hajalipwa")).toBeDefined();
  });

  it("words the demo's ready reason for a correction", async () => {
    const demo = {
      ...NEEMA,
      kept_lines: [
        kept("full", "24000.00", { days: 3, each: "8000.00" }),
        kept("correction", "9000.00", { note: "day_not_counted" }),
      ],
      total: "33000.00",
    };
    theShopPays(
      payMonth([demo], {
        total: "33000.00",
        approval: APPROVED,
        still_to_pay: "33000.00",
      }),
    );
    render(<PrintedPayslipsScreen asked="2026-11" staff={null} />);

    const [slip] = await payslips();
    expect(
      within(slip as HTMLElement).getByText("Marekebisho: Siku haikuhesabiwa"),
    ).toBeDefined();
  });

  it("has nothing to print of a month still open, nor of a worker with no payslip", async () => {
    theShopPays(payMonth([ASHA_DRAFT], { total: "152000.00" }));
    const { unmount } = render(
      <PrintedPayslipsScreen asked="2026-11" staff={null} />,
    );

    expect(
      await screen.findByText(
        "Hati ya malipo inapatikana malipo yakishaidhinishwa.",
      ),
    ).toBeDefined();
    expect(screen.queryByRole("table")).toBeNull();
    // Mishahara's arrow, when it was opened from there.
    fireEvent.click(screen.getByRole("button", { name: "Rudi ulipotoka" }));
    expect(router.push).toHaveBeenCalledWith("/pay/?month=2026-11");
    unmount();

    render(<PrintedPayslipsScreen asked="2026-11" staff={ASHA_DRAFT.staff} />);
    expect(
      await screen.findByText(
        "Hati ya malipo inapatikana malipo yakishaidhinishwa.",
      ),
    ).toBeDefined();
  });
});
