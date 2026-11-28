// pay-papers.tsx — the ways to the papers of an approved month (WAGE-5), where the month is read:
//
//   Mishahara, an approved month           [ Chapisha orodha ] [ Chapisha hati za malipo ] [ Pakua Excel ]
//   a worker's pay page, with a payslip    [ Chapisha hati ya malipo ]
//
// The sheet (month-sheet.tsx) and the payslips (printed-payslips.tsx) are pages of their own, each with Chapisha, as a
// record has a page of its own (Jack, CTRL-4); the Excel file (pay-excel.ts) is written here, at the tap, and handed to
// the browser to save. Only once the month is approved, or, on a worker's page, once their own payslip is kept, as a
// leaver's is before the month's: a draft can still change. For whoever reads the pay, as the pages they sit on are.
//
// "use client": it asks use-intl for words (use-client.test.ts), and keeps whether the file is being made.
"use client";

import { useState } from "react";
import { useTranslations } from "use-intl";

import { Button, ButtonLink } from "@/components/design/button";

import {
  type Approval,
  monthSheetPage,
  type PayMonth,
  payslipsPage,
  type WorkerPay,
} from "./pay";
import { savePayExcel, useExcelWords } from "./pay-excel";

/** Mishahara's three, of an approved month. */
export function MonthPapers({
  answer,
  approval,
  timezone,
}: {
  answer: PayMonth;
  /** Who approved it and when: the papers are of an approved month only. */
  approval: Approval;
  /** The shop's, for each day the file names. */
  timezone: string;
}) {
  const t = useTranslations("pay.papers");
  const words = useExcelWords(answer.month, approval, timezone);
  // While the file is made, its button waits, so a second tap makes no second file; a failure says so under it.
  const [making, setMaking] = useState(false);
  const [failed, setFailed] = useState(false);

  async function download() {
    setMaking(true);
    setFailed(false);
    try {
      await savePayExcel(answer, words, timezone);
    } catch {
      // The library's own file not loaded, or an amount the file refuses (asCellNumber): nothing is saved.
      setFailed(true);
    } finally {
      setMaking(false);
    }
  }

  return (
    <div className="grid gap-2">
      <div className="flex flex-wrap gap-2">
        <ButtonLink
          kind="second"
          size="normal"
          href={monthSheetPage(answer.month)}
        >
          {t("printSheet")}
        </ButtonLink>
        <ButtonLink
          kind="second"
          size="normal"
          href={payslipsPage(answer.month)}
        >
          {t("printPayslips")}
        </ButtonLink>
        <Button
          kind="second"
          size="normal"
          disabled={making}
          onClick={() => void download()}
        >
          {t("excel")}
        </Button>
      </div>
      {failed ? <p role="alert">{t("excelFailed")}</p> : null}
    </div>
  );
}

/** A worker's pay page's one, once a payslip keeps their pay. */
export function PayslipPaper({
  worker,
  month,
}: {
  worker: WorkerPay;
  month: string;
}) {
  const t = useTranslations("pay.papers");
  if (worker.payslip === null) return null;
  return (
    <ButtonLink
      kind="second"
      size="normal"
      className="justify-self-start"
      href={payslipsPage(month, worker.staff)}
    >
      {t("printPayslip")}
    </ButtonLink>
  );
}
