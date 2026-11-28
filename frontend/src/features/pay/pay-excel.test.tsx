// pay-excel.test.tsx — an approved month's pay as an Excel file (WAGE-5): Jack's four rows and the total, as he drew
// them (28 Nov 2026), in the person's own language; the money a number only in the file's cells, in whole shillings or
// refused; and a real file written and handed to the browser, read back here with Node's own zip reader, so the
// amounts are proven to be numbers in it, not text. Fake data only: every name, amount and number is made up (rule 10).
import { renderHook } from "@testing-library/react";
import { inflateRawSync } from "node:zlib";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LanguageProvider } from "@/i18n/provider";
import { setLanguage } from "@/i18n/language";
import {
  pay,
  payment,
  type PayMonth,
  payMonth,
  type WorkerPay,
  workerPay,
} from "@/test/pay";

import {
  asCellNumber,
  excelFileName,
  type ExcelWords,
  payRows,
  savePayExcel,
  useExcelWords,
} from "./pay-excel";

const TIMEZONE = "Africa/Dar_es_Salaam";
/** Approved by Baba at 09:00 on 1 December in Arusha. */
const APPROVED = { by: "Baba", at: "2026-12-01T06:00:00Z" };

function line(
  paid_as: "full" | "half",
  days: number,
  each: string,
  amount: string,
) {
  return { paid_as, days, each, amount };
}

/** A payslip's worker line, approved, as Mishahara answers it: the line's sums as the server adds them. */
function slip(fields: Partial<WorkerPay>): WorkerPay {
  return workerPay({
    payslip: "019a8900-0000-7000-8000-000000000001",
    approval: APPROVED,
    to_hand_out: "0.00",
    ...fields,
  });
}

/** November as Jack drew it. */
const NOVEMBER: PayMonth = payMonth(
  [
    slip({
      display_name: "Asha",
      total: "152000.00",
      pay: pay({
        lines: [
          line("full", 20, "9000.00", "180000.00"),
          line("half", 2, "4500.00", "9000.00"),
        ],
        fined_days: 2,
        fines: "1000.00",
        meal_days: 22,
        meals: "16000.00",
        advances: "20000.00",
        total: "152000.00",
      }),
      payments: [payment()],
    }),
    slip({
      display_name: "Baraka",
      total: "117000.00",
      pay: pay({
        lines: [line("full", 15, "9000.00", "135000.00")],
        fined_days: 4,
        fines: "2000.00",
        meal_days: 15,
        meals: "16000.00",
        total: "117000.00",
      }),
      payments: [
        payment({
          method: "mobile_money",
          reference: "QJK7A2B9XC",
          amount: "117000.00",
          signature: null,
        }),
      ],
    }),
    slip({
      display_name: "Juma",
      total: "163000.00",
      pay: pay({
        lines: [
          line("full", 17, "10000.00", "170000.00"),
          line("half", 1, "5000.00", "5000.00"),
        ],
        fined_days: 2,
        fines: "1000.00",
        meal_days: 18,
        meals: "20000.00",
        corrections: "9000.00",
        total: "163000.00",
      }),
      payments: [payment({ amount: "163000.00", at: "2026-12-03T05:30:00Z" })],
    }),
    slip({
      display_name: "Neema",
      total: "-18000.00",
      pay: pay({
        lines: [line("full", 3, "8000.00", "24000.00")],
        fined_days: 0,
        fines: "0.00",
        meal_days: 3,
        meals: "4000.00",
        advances: "20000.00",
        carried: "18000.00",
        total: "-18000.00",
      }),
    }),
    // A worker still on a draft has no payslip, and no row: only kept payslips are in the file.
    workerPay({ display_name: "Zawadi", total: "5000.00" }),
  ],
  { total: "432000.00", approval: APPROVED, still_to_pay: "0.00" },
);

/** The file's words in the books' own language, as the page gets them. */
function wordsFor(month: PayMonth): ExcelWords {
  function Books({ children }: { children: ReactNode }) {
    return <LanguageProvider>{children}</LanguageProvider>;
  }
  return renderHook(() => useExcelWords(month.month, APPROVED, TIMEZONE), {
    wrapper: Books,
  }).result.current;
}

/** Each row's values alone, as Excel shows them before its formats; null for an empty cell. */
function valuesOf(month: PayMonth): unknown[][] {
  return payRows(month, wordsFor(month), TIMEZONE).map((row) =>
    row.map((cell) =>
      cell !== null && typeof cell === "object" && "value" in cell
        ? cell.value
        : (cell ?? null),
    ),
  );
}

afterEach(() => {
  vi.restoreAllMocks();
  setLanguage("sw");
});

describe("the month's pay as an Excel file", () => {
  it("has Jack's rows and the total, in Swahili", () => {
    expect(valuesOf(NOVEMBER)).toEqual([
      ["Mishahara ya Novemba 2026 · Imeidhinishwa na Baba · 01/12/2026"],
      [],
      [
        "Jina",
        "Kwa siku",
        "Siku kamili",
        "Nusu siku",
        "Faini",
        "Chakula",
        "Advansi",
        "Deni",
        "Marekebisho",
        "Jumla",
        "Analipwa",
        "Tarehe",
        "Njia",
        "Namba ya muamala",
      ],
      [
        "Asha",
        9000,
        20,
        2,
        -1000,
        -16000,
        -20000,
        0,
        0,
        152000,
        152000,
        "02/12/2026",
        "Taslimu",
        null,
      ],
      [
        "Baraka",
        9000,
        15,
        0,
        -2000,
        -16000,
        0,
        0,
        0,
        117000,
        117000,
        "02/12/2026",
        "M-Pesa",
        "QJK7A2B9XC",
      ],
      [
        "Juma",
        10000,
        17,
        1,
        -1000,
        -20000,
        0,
        0,
        9000,
        163000,
        163000,
        "03/12/2026",
        "Taslimu",
        null,
      ],
      [
        "Neema",
        8000,
        3,
        0,
        0,
        -4000,
        -20000,
        -18000,
        0,
        -18000,
        0,
        null,
        "Hakulipwa",
        null,
      ],
      [
        "Jumla",
        null,
        null,
        null,
        null,
        null,
        null,
        null,
        null,
        null,
        432000,
        null,
        null,
        null,
      ],
    ]);
  });

  it("writes the money as numbers with a thousands comma, and the words and days as text", () => {
    const rows = payRows(NOVEMBER, wordsFor(NOVEMBER), TIMEZONE);
    const asha = rows[3] ?? [];
    expect(asha[9]).toEqual({ value: 152000, type: Number, format: "#,##0" });
    expect(asha[0]).toEqual({ value: "Asha", type: String, format: "@" });
    // "02/12/2026" stays text, so Excel never guesses a date of its own.
    expect(asha[11]).toEqual({
      value: "02/12/2026",
      type: String,
      format: "@",
    });
  });

  it("says Hajalipwa of one not paid yet, with what is still to hand over", () => {
    const month = payMonth(
      [
        slip({
          display_name: "Baraka",
          total: "117000.00",
          to_hand_out: "117000.00",
        }),
      ],
      {
        total: "117000.00",
        approval: APPROVED,
      },
    );
    expect(valuesOf(month)[3]?.slice(10)).toEqual([
      117000,
      null,
      "Hajalipwa",
      null,
    ]);
  });

  it("says nothing in Njia of a payslip of exactly 0: neither Hajalipwa nor Hakulipwa", () => {
    const month = payMonth(
      [slip({ display_name: "Baraka", total: "0.00", to_hand_out: "0.00" })],
      {
        total: "0.00",
        approval: APPROVED,
      },
    );
    expect(valuesOf(month)[3]?.slice(9)).toEqual([0, 0, null, null, null]);
  });

  it("says both rates of one whose rate changed in the month", () => {
    const month = payMonth(
      [
        slip({
          display_name: "Asha",
          total: "22000.00",
          pay: pay({
            lines: [
              line("full", 1, "10000.00", "10000.00"),
              line("full", 1, "12000.00", "12000.00"),
            ],
          }),
        }),
      ],
      { total: "22000.00", approval: APPROVED },
    );
    expect(valuesOf(month)[3]?.slice(0, 3)).toEqual([
      "Asha",
      "10,000 / 12,000",
      2,
    ]);
  });

  it("is in English for whoever reads English", () => {
    setLanguage("en");
    expect(valuesOf(NOVEMBER)[0]).toEqual([
      "Pay for November 2026 · Approved by Baba · 01/12/2026",
    ]);
    expect(valuesOf(NOVEMBER)[6]?.[12]).toBe("Not paid");
  });

  it("takes only whole shillings into a cell, never rounding a part away", () => {
    expect(asCellNumber("-18000.00")).toBe(-18000);
    expect(asCellNumber("0.00")).toBe(0);
    expect(() => asCellNumber("1000.50")).toThrow(RangeError);
    // Past what a number holds exactly.
    expect(() => asCellNumber("90071992547409930.00")).toThrow(RangeError);
  });

  it("names the file by its month", () => {
    expect(excelFileName("2026-11")).toBe("mishahara-2026-11.xlsx");
  });

  it("writes a real Excel file, its money numbers in it, and hands it to the browser to save", async () => {
    // jsdom has no file links and saves nothing: the link the library makes is caught as it is clicked.
    let made: Blob | undefined;
    URL.createObjectURL = vi.fn((blob: Blob) => {
      made = blob;
      return "blob:the-file";
    });
    URL.revokeObjectURL = vi.fn();
    const saved: string[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      saved.push(this.download);
    });

    await savePayExcel(NOVEMBER, wordsFor(NOVEMBER), TIMEZONE);

    expect(saved).toEqual(["mishahara-2026-11.xlsx"]);
    expect(made?.type).toBe(
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    );
    const sheet = entryOf(
      new Uint8Array(await (made as Blob).arrayBuffer()),
      "xl/worksheets/sheet1.xml",
    );
    // Asha's total, a number cell (no t="s" or "inlineStr"): Excel adds it up and sorts it as a number.
    expect(sheet).toMatch(/<c r="J4"[^>]*><v>152000<\/v><\/c>/);
    expect(sheet).not.toMatch(/<c r="J4"[^>]* t="/);
  });
});

/** One file inside a zip, read through the zip's own table of contents (its central directory), then inflated by Node's
 * zlib: an .xlsx is a zip of XML files. */
function entryOf(zip: Uint8Array, name: string): string {
  const view = new DataView(zip.buffer, zip.byteOffset, zip.byteLength);
  const text = new TextDecoder();
  for (let at = 0; at + 46 <= zip.length; at += 1) {
    if (view.getUint32(at, true) !== 0x02014b50) continue;
    const method = view.getUint16(at + 10, true);
    const size = view.getUint32(at + 20, true);
    const nameLength = view.getUint16(at + 28, true);
    const local = view.getUint32(at + 42, true);
    if (text.decode(zip.subarray(at + 46, at + 46 + nameLength)) !== name)
      continue;
    const start =
      local +
      30 +
      view.getUint16(local + 26, true) +
      view.getUint16(local + 28, true);
    const data = zip.subarray(start, start + size);
    return text.decode(method === 0 ? data : inflateRawSync(data));
  }
  throw new Error(`${name} is not in the file`);
}
