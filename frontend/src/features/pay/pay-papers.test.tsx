// pay-papers.test.tsx — the ways to an approved month's papers (WAGE-5): Mishahara's three, the sheet, the payslips and
// the Excel file, written at the tap and held while it is made, a failure said; and a worker's own payslip, once one is
// kept. Fake data only: every name and amount is made up (rule 10).
import { act, fireEvent, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { payment, payMonth, workerPay } from "@/test/pay";
import { render } from "@/test/render";

import { savePayExcel } from "./pay-excel";
import { MonthPapers, PayslipPaper } from "./pay-papers";

// The file itself is pay-excel.test.tsx's: here, only that the tap asks for it, with the month and its words.
vi.mock("./pay-excel", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./pay-excel")>()),
  savePayExcel: vi.fn(),
}));

const APPROVED = { by: "Baba", at: "2026-12-01T06:00:00Z" };
const NOVEMBER = payMonth(
  [
    workerPay({
      display_name: "Asha",
      total: "152000.00",
      payslip: "019a8900-0000-7000-8000-000000000001",
      approval: APPROVED,
      payments: [payment()],
    }),
  ],
  { total: "152000.00", approval: APPROVED, still_to_pay: "0.00" },
);

afterEach(() => {
  vi.mocked(savePayExcel).mockReset();
});

describe("an approved month's papers on Mishahara", () => {
  it("opens the sheet and the payslips on pages of their own, of the same month", () => {
    render(
      <MonthPapers
        answer={NOVEMBER}
        approval={APPROVED}
        timezone="Africa/Dar_es_Salaam"
      />,
    );

    expect(
      screen
        .getByRole("link", { name: "Chapisha orodha" })
        .getAttribute("href"),
    ).toBe("/pay/sheet?month=2026-11");
    expect(
      screen
        .getByRole("link", { name: "Chapisha hati za malipo" })
        .getAttribute("href"),
    ).toBe("/pay/payslips?month=2026-11");
  });

  it("writes the Excel file at the tap, in the person's words, and holds while it is made", async () => {
    let done = () => {};
    vi.mocked(savePayExcel).mockImplementation(
      () => new Promise<void>((resolve) => (done = resolve)),
    );
    render(
      <MonthPapers
        answer={NOVEMBER}
        approval={APPROVED}
        timezone="Africa/Dar_es_Salaam"
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Pakua Excel" }));

    expect(savePayExcel).toHaveBeenCalledOnce();
    const [answer, words, timezone] =
      vi.mocked(savePayExcel).mock.calls[0] ?? [];
    expect(answer).toBe(NOVEMBER);
    expect(words?.title).toBe(
      "Mishahara ya Novemba 2026 · Imeidhinishwa na Baba · 01/12/2026",
    );
    expect(timezone).toBe("Africa/Dar_es_Salaam");
    // A second tap while it is made makes no second file.
    expect(screen.getByRole("button", { name: "Pakua Excel" })).toHaveProperty(
      "disabled",
      true,
    );
    await act(async () => done());
    expect(screen.getByRole("button", { name: "Pakua Excel" })).toHaveProperty(
      "disabled",
      false,
    );
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("says so when the file can't be made, and lets the person try again", async () => {
    vi.mocked(savePayExcel).mockRejectedValueOnce(
      new RangeError("Not a whole number of shillings: 1.50"),
    );
    render(
      <MonthPapers
        answer={NOVEMBER}
        approval={APPROVED}
        timezone="Africa/Dar_es_Salaam"
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Pakua Excel" }));

    expect((await screen.findByRole("alert")).textContent).toBe(
      "Faili la Excel halikuweza kutengenezwa. Jaribu tena.",
    );
    expect(screen.getByRole("button", { name: "Pakua Excel" })).toHaveProperty(
      "disabled",
      false,
    );
  });
});

describe("a worker's payslip on their pay page", () => {
  it("opens their payslip alone, once one is kept", () => {
    const asha = NOVEMBER.workers[0];
    if (asha === undefined) throw new Error("no Asha");
    render(<PayslipPaper worker={asha} month="2026-11" />);

    expect(
      screen
        .getByRole("link", { name: "Chapisha hati ya malipo" })
        .getAttribute("href"),
    ).toBe(`/pay/payslips?month=2026-11&staff=${asha.staff}`);
  });

  it("offers nothing on a draft, which no payslip keeps", () => {
    render(
      <PayslipPaper
        worker={workerPay({ display_name: "Asha" })}
        month="2026-11"
      />,
    );

    expect(screen.queryByRole("link")).toBeNull();
  });
});
