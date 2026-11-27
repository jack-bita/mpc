// my-pay.test.tsx — Malipo, a worker's own pay of the month (WAGE-4), as Jack drew it: an open month counted so far and
// said to be not approved yet; an approved one with who approved it and how it was handed out, its number to check; a
// payment crossed out, struck through; nothing paid yet; a debt said to the worker; no daily pay; and nothing to change.
import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { components } from "@/api/schema";
import { render } from "@/test/render";

import { MyPay } from "./my-pay";

type OwnPay = components["schemas"]["OwnPayAnswer"];
type Pay = components["schemas"]["Pay"];
type OwnPayment = components["schemas"]["OwnPayment"];

const ARUSHA = "Africa/Dar_es_Salaam";

/** Asha's November so far, as Jack drew it: 20 full days and a half at 9,000, two fines, 21 days of meals, an advance. */
const SO_FAR: Pay = {
  lines: [
    { paid_as: "full", days: 20, each: "9000.00", amount: "180000.00" },
    { paid_as: "half", days: 1, each: "4500.00", amount: "4500.00" },
  ],
  fined_days: 2,
  fines: "1000.00",
  meal_days: 21,
  meals: "31500.00",
  advances: "20000.00",
  carried: "0.00",
  corrections: "0.00",
  waiting: 0,
  no_rate: 0,
  total: "132000.00",
};

const NOVEMBER: OwnPay = {
  month: "2026-11",
  today: "2026-11-27",
  counted_to: "2026-11-26",
  paid_by_day: true,
  no_day_yet: false,
  line: {
    left_on: null,
    pay: SO_FAR,
    today: null,
    total: "132000.00",
    carried_from: null,
    approval: null,
    to_hand_out: "0.00",
    payments: [],
  },
  corrections: [],
  void_reasons: [],
};

function payment(changes: Partial<OwnPayment>): OwnPayment {
  return {
    id: "019a8400-0000-7000-8000-0000000000f1",
    method: "mobile_money",
    reference: "QK7H2M9XPL",
    amount: "159500.00",
    by: "Baba",
    // 10:15 in Arusha on 1 November.
    at: "2026-11-01T07:15:00Z",
    voided: null,
    ...changes,
  };
}

/** Asha's October, approved by Baba on 1 November at 09:00 and handed out. */
function october(payments: OwnPayment[]): OwnPay {
  return {
    ...NOVEMBER,
    month: "2026-10",
    counted_to: "2026-10-31",
    line: {
      ...NOVEMBER.line,
      total: "159500.00",
      pay: { ...SO_FAR, total: "159500.00" },
      approval: { by: "Baba", at: "2026-11-01T06:00:00Z" },
      to_hand_out: payments.some((made) => made.voided === null)
        ? "0.00"
        : "159500.00",
      payments,
    },
  };
}

function show(answer: OwnPay) {
  const { container } = render(<MyPay answer={answer} timezone={ARUSHA} />);
  return container;
}

describe("a worker's own pay", () => {
  it("shows an open month counted so far, said to be not approved yet, with its total said to the worker", () => {
    const page = show(NOVEMBER);
    expect(page.textContent).toContain("Hadi jana, Alhamisi 26/11");
    expect(page.textContent).toContain(
      "Bado hayajaidhinishwa, yanaweza kubadilika.",
    );
    const lines = screen.getByRole("table");
    expect(lines.textContent).toContain("Siku kamili20 × 9,000180,000");
    expect(lines.textContent).toContain("Advansi− 20,000");
    // Said to her: what she is paid today, not what Baba pays "him".
    expect(lines.textContent).toMatch(/Jumla ya kulipwa leoTSh\s132,000/);
  });

  it("shows an approved month with who approved it and how it was paid, with the number to check", () => {
    const page = show(october([payment({})]));
    expect(page.textContent).toContain(
      "Imeidhinishwa na Baba · 01/11/2026 09:00 asubuhi",
    );
    expect(page.textContent).not.toContain("Bado hayajaidhinishwa");
    expect(screen.getByRole("table").textContent).toMatch(
      /Jumla ya mweziTSh\s159,500/,
    );
    const handedOut = screen.getByRole("region", { name: "Malipo yake" });
    expect(handedOut.textContent).toContain(
      "Umelipwa kwa M-Pesa na Baba · 01/11/2026 10:15 asubuhi",
    );
    expect(handedOut.textContent).toContain("Namba ya muamala: QK7H2M9XPL");
  });

  it("offers nothing to change: no Lipa, Batilisha or Ongeza marekebisho, and no signature", () => {
    show(october([payment({ method: "cash", reference: "" })]));
    expect(screen.queryAllByRole("button")).toEqual([]);
    expect(screen.queryByRole("img")).toBeNull();
    expect(
      screen.getByRole("region", { name: "Malipo yake" }).textContent,
    ).toBe("Umelipwa taslimu na Baba · 01/11/2026 10:15 asubuhi");
  });

  it("shows a payment crossed out, struck through, with who and why, and then the one that counts", () => {
    show(
      october([
        payment({
          id: "019a8400-0000-7000-8000-0000000000f0",
          voided: {
            by: "Baba",
            at: "2026-11-01T07:30:00Z",
            reason: "Nilibonyeza mfanyakazi mwingine",
          },
        }),
        payment({ method: "cash", reference: "" }),
      ]),
    );
    const handedOut = screen.getByRole("region", { name: "Malipo yake" });
    const struck = within(handedOut).getByText(
      "Umelipwa kwa M-Pesa na Baba · 01/11/2026 10:15 asubuhi",
    );
    expect(struck.tagName).toBe("S");
    expect(handedOut.textContent).toContain(
      "Imebatilishwa na Baba · 01/11/2026 10:30 asubuhi: Nilibonyeza mfanyakazi mwingine",
    );
    expect(handedOut.textContent).toContain(
      "Umelipwa taslimu na Baba · 01/11/2026 10:15 asubuhi",
    );
  });

  it("says when an approved month is not paid yet", () => {
    show(october([]));
    expect(
      screen.getByRole("region", { name: "Malipo yake" }).textContent,
    ).toBe("Bado hujalipwa.");
  });

  it("says a debt to the worker, not of them", () => {
    const owing = october([]);
    show({
      ...owing,
      line: { ...owing.line, total: "-18000.00", to_hand_out: "0.00" },
    });
    expect(document.body.textContent).toMatch(
      /Ulilipwa 0\. Ulibaki unadaiwa TSh\s18,000\./,
    );
  });

  it("says in one sentence that there is no daily pay this month", () => {
    const page = show({ ...NOVEMBER, paid_by_day: false });
    expect(page.textContent).toBe("Huna malipo kwa siku mwezi huu.");
  });

  it("says nothing on a month whose first working day is still to come", () => {
    const page = show({ ...NOVEMBER, paid_by_day: false, no_day_yet: true });
    expect(page.textContent).toBe("");
  });
});
