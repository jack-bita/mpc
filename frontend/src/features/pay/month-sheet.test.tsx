// month-sheet.test.tsx — the month's sheet (WAGE-5): every payment of an approved month, each with its proof and a
// space to sign by pen, as Jack drew it (28 Nov 2026); one not paid yet, one who owes, one crossed out, the demo's, a
// drawing that can't be opened; and nothing to print of a month still open. Fake data only: every name, amount and
// number is made up (rule 10).
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { photoAddress } from "@/lib/photo-address";
import { answer, refusal, sent } from "@/test/fake-server";
import {
  OWNER,
  PAY_ROUTE,
  payment,
  type PayMonth,
  payMonth,
  workerPay,
} from "@/test/pay";
import { render } from "@/test/render";
import { router } from "@/test/router";

import { MonthSheetScreen } from "./month-sheet";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

const ME = "/api/auth/me/";

/** Approved by Baba at 09:00 on 1 December in Arusha. */
const APPROVED = { by: "Baba", at: "2026-12-01T06:00:00Z" };

/** November as Jack drew it: Asha and Juma paid in cash, each signed; Baraka by M-Pesa; Neema owes 18,000. */
const NOVEMBER = payMonth(
  [
    workerPay({
      display_name: "Asha",
      total: "152000.00",
      payslip: "019a8900-0000-7000-8000-000000000001",
      approval: APPROVED,
      payments: [payment()],
    }),
    workerPay({
      display_name: "Baraka",
      total: "117000.00",
      payslip: "019a8900-0000-7000-8000-000000000002",
      approval: APPROVED,
      payments: [
        payment({
          id: "019a8700-0000-7000-8000-000000000002",
          method: "mobile_money",
          reference: "QJK7A2B9XC",
          amount: "117000.00",
          signature: null,
        }),
      ],
    }),
    workerPay({
      display_name: "Juma",
      total: "163000.00",
      payslip: "019a8900-0000-7000-8000-000000000003",
      approval: APPROVED,
      payments: [
        payment({
          id: "019a8700-0000-7000-8000-000000000003",
          amount: "163000.00",
          at: "2026-12-03T05:30:00Z",
          signature: "019a8700-0000-7000-8000-0000000000a3",
        }),
      ],
    }),
    workerPay({
      display_name: "Neema",
      total: "-18000.00",
      payslip: "019a8900-0000-7000-8000-000000000004",
      approval: APPROVED,
    }),
  ],
  { total: "432000.00", approval: APPROVED, still_to_pay: "0.00" },
);

/** Baba is logged in, and the server answers this month's pay. */
function theShopPays(month: PayMonth, who = OWNER) {
  answer("GET", ME, { status: 200, body: who });
  answer("GET", PAY_ROUTE, { status: 200, body: month });
}

/** A part's words, with the plain space people type for the one Intl writes after "TSh". */
function wordsOf(part: Element | null): string {
  return (part?.textContent ?? "").replace(/[\u00a0\u202f]/g, " ").trim();
}

/** The sheet's rows, each as its cells' words. */
async function rows(): Promise<string[][]> {
  const table = await screen.findByRole("table");
  return within(table)
    .getAllByRole("row")
    .slice(1)
    .map((row) => [...row.querySelectorAll("td")].map(wordsOf));
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

describe("the month's sheet", () => {
  it("lists every payment of the month, as Jack drew it", async () => {
    theShopPays(NOVEMBER);
    render(<MonthSheetScreen asked="2026-11" />);

    expect(await rows()).toEqual([
      ["1", "Asha", "152,000", "02/12/2026", "Taslimu", "", ""],
      ["2", "Baraka", "117,000", "02/12/2026", "M-Pesa QJK7A2B9XC", "—", ""],
      ["3", "Juma", "163,000", "03/12/2026", "Taslimu", "", ""],
      ["4", "Neema", "0", "—", "Hakulipwa: deni 18,000", "—", ""],
    ]);
    // The columns, in the order he drew them.
    expect(
      screen.getAllByRole("columnheader").map((heading) => heading.textContent),
    ).toEqual([
      "Na.",
      "Jina",
      "Kiasi",
      "Tarehe",
      "Njia",
      "Sahihi",
      "Sahihi kwa kalamu",
    ]);
    // The two drawings, each in its own row, from the photos' own route.
    const asha = screen.getByRole("img", { name: "Sahihi ya Asha" });
    expect(
      new URL(asha.getAttribute("src") ?? "", "http://shop").pathname,
    ).toBe(photoAddress("019a8700-0000-7000-8000-0000000000a1"));
    expect(screen.getByRole("img", { name: "Sahihi ya Juma" })).toBeDefined();
    // Each fetched at once, never lazily as it nears the screen: Chapisha waits for every one (WAGE-5's review).
    expect(
      screen
        .getAllByRole("img")
        .map((picture) => picture.getAttribute("loading")),
    ).toEqual(["eager", "eager"]);
    // The top and the foot.
    expect(screen.getByRole("heading", { level: 2 }).textContent).toBe(
      "Mishahara ya Novemba 2026",
    );
    expect(
      screen.getByText("Imeidhinishwa na Baba · 01/12/2026 09:00 asubuhi"),
    ).toBeDefined();
    expect(wordsOf(screen.getByText(/^Jumla ya wote/))).toBe(
      "Jumla ya wote: TSh 432,000",
    );
    expect(screen.getByText("Sahihi ya aliyelipa:")).toBeDefined();
    // The shop's name on top, alone, as its code is the same.
    expect(screen.getByText("MPC")).toBeDefined();
  });

  it("names the shop by its code and its name, when they differ", async () => {
    theShopPays(NOVEMBER, {
      ...OWNER,
      shop: { ...OWNER.shop, name: "Mabatini Pumba Center" },
    });
    render(<MonthSheetScreen asked="2026-11" />);

    expect(
      await screen.findByText("MPC · Mabatini Pumba Center"),
    ).toBeDefined();
  });

  it("says Hajalipwa of one not paid yet, their boxes empty", async () => {
    theShopPays(
      payMonth(
        [
          workerPay({
            display_name: "Baraka",
            total: "117000.00",
            payslip: "019a8900-0000-7000-8000-000000000002",
            approval: APPROVED,
            to_hand_out: "117000.00",
          }),
        ],
        { total: "117000.00", approval: APPROVED, still_to_pay: "117000.00" },
      ),
    );
    render(<MonthSheetScreen asked="2026-11" />);

    expect(await rows()).toEqual([
      ["1", "Baraka", "117,000", "", "Hajalipwa", "", ""],
    ]);
  });

  it("says neither Hajalipwa nor a debt of a payslip of exactly 0", async () => {
    // Baraka earned 117,000 and took 117,000 before payday: nothing to hand over, nothing owed, and so no Lipa. The
    // paper says a dash, never Hajalipwa, which would stand on it for ever (WAGE-5's review).
    theShopPays(
      payMonth(
        [
          workerPay({
            display_name: "Baraka",
            total: "0.00",
            payslip: "019a8900-0000-7000-8000-000000000002",
            approval: APPROVED,
            to_hand_out: "0.00",
          }),
        ],
        { total: "0.00", approval: APPROVED, still_to_pay: "0.00" },
      ),
    );
    render(<MonthSheetScreen asked="2026-11" />);

    expect(await rows()).toEqual([["1", "Baraka", "0", "—", "—", "—", ""]]);
  });

  it("shows only the payment that counts, never one crossed out", async () => {
    // Asha was marked paid by M-Pesa by mistake, crossed out, then paid in cash and signed: the sheet has the cash
    // alone. And Baraka's one payment was crossed out, so he waits again.
    theShopPays(
      payMonth(
        [
          workerPay({
            display_name: "Asha",
            total: "152000.00",
            payslip: "019a8900-0000-7000-8000-000000000001",
            approval: APPROVED,
            payments: [
              payment({
                id: "019a8700-0000-7000-8000-000000000009",
                method: "mobile_money",
                reference: "QX1",
                signature: null,
                voided: {
                  by: "Baba",
                  at: "2026-12-02T05:00:00Z",
                  reason: "Si yeye",
                },
              }),
              payment(),
            ],
          }),
          workerPay({
            display_name: "Baraka",
            total: "117000.00",
            payslip: "019a8900-0000-7000-8000-000000000002",
            approval: APPROVED,
            to_hand_out: "117000.00",
            payments: [
              payment({
                id: "019a8700-0000-7000-8000-000000000008",
                amount: "117000.00",
                voided: {
                  by: "Baba",
                  at: "2026-12-02T05:20:00Z",
                  reason: "Si yeye",
                },
              }),
            ],
          }),
        ],
        { total: "269000.00", approval: APPROVED, still_to_pay: "117000.00" },
      ),
    );
    render(<MonthSheetScreen asked="2026-11" />);

    expect(await rows()).toEqual([
      ["1", "Asha", "152,000", "02/12/2026", "Taslimu", "", ""],
      ["2", "Baraka", "117,000", "", "Hajalipwa", "", ""],
    ]);
    expect(screen.queryByText(/QX1/)).toBeNull();
    // Baraka's crossed-out drawing isn't on the paper: Asha's alone.
    expect(
      screen.getAllByRole("img").map((picture) => picture.getAttribute("alt")),
    ).toEqual(["Sahihi ya Asha"]);
  });

  it("says the demo keeps no signature", async () => {
    theShopPays(
      payMonth(
        [
          workerPay({
            display_name: "Asha",
            total: "152000.00",
            payslip: "019a8900-0000-7000-8000-000000000001",
            approval: APPROVED,
            payments: [payment({ signature: null, no_signature: "demo" })],
          }),
        ],
        {
          total: "152000.00",
          approval: APPROVED,
          still_to_pay: "0.00",
          keeps_signatures: false,
        },
      ),
    );
    render(<MonthSheetScreen asked="2026-11" />);

    expect((await rows())[0]?.[5]).toBe("Kwenye demo, sahihi haihifadhiwi.");
  });

  it("says so of a drawing that can't be opened, never a box that looks signed", async () => {
    theShopPays(NOVEMBER);
    render(<MonthSheetScreen asked="2026-11" />);

    fireEvent.error(await screen.findByRole("img", { name: "Sahihi ya Asha" }));

    expect((await rows())[0]?.[5]).toBe("Sahihi haikuweza kufunguka.");
  });

  it("has nothing to print of a month still open", async () => {
    theShopPays(
      payMonth([workerPay({ display_name: "Asha", total: "152000.00" })], {
        total: "152000.00",
      }),
    );
    render(<MonthSheetScreen asked="2026-11" />);

    expect(
      await screen.findByText("Orodha hii inapatikana mwezi ukishaidhinishwa."),
    ).toBeDefined();
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.queryByText("Asha")).toBeNull();
    // Nothing to print: Chapisha would print a blank page.
    expect(screen.getByRole("button", { name: "Chapisha" })).toHaveProperty(
      "disabled",
      true,
    );
  });

  it("asks nothing with no month in the address", async () => {
    theShopPays(NOVEMBER);
    render(<MonthSheetScreen asked="november" />);

    expect(
      await screen.findByText("Orodha hii inapatikana mwezi ukishaidhinishwa."),
    ).toBeDefined();
    await waitFor(() =>
      expect(sent.some((request) => request.url.includes(ME))).toBe(true),
    );
    expect(
      sent.some((request) => new URL(request.url).pathname === PAY_ROUTE),
    ).toBe(false);
  });

  it("shows the server's refusal to someone without the keys of pay", async () => {
    answer("GET", ME, { status: 200, body: OWNER });
    answer("GET", PAY_ROUTE, refusal(403, "permission_denied"));
    render(<MonthSheetScreen asked="2026-11" />);

    expect(await screen.findByRole("alert")).toBeDefined();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("goes back to Mishahara on the same month", async () => {
    theShopPays(NOVEMBER);
    render(<MonthSheetScreen asked="2026-11" />);
    await rows();

    fireEvent.click(screen.getByRole("button", { name: "Rudi ulipotoka" }));

    expect(router.push).toHaveBeenCalledWith("/pay/?month=2026-11");
  });
});
