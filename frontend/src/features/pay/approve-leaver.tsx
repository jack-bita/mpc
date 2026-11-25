// approve-leaver.tsx — the sheet that approves the pay of one worker who left, alone, over their own pay page (WAGE-3), as
// Jack pictured it (25 Nov 2026): Neema taps Toka on the 14th, Baba reads her 62,000, and approves it that evening, as she
// can't wait for the month's end:
//
//   ┌──────────────────────────────────┐
//   │ Idhinisha malipo ya Neema        │
//   │ Novemba 2026 · Jumla TSh 62,000  │
//   │ Baada ya kuidhinisha, malipo yake│
//   │ ya Novemba 2026 hayabadiliki     │
//   │ tena.                            │
//   │ [ Ghairi ]         [ Idhinisha ] │
//   └──────────────────────────────────┘
//
// What stops it is of their own days alone, and their Toka on their last evening (approve-sheet.tsx). It sends the total
// as the page showed it when the sheet opened, so whoever approves approves only what they read (approve-month.tsx). How
// it is sent, and what is read again after it, is useApproval's (use-approval.ts).
//
// "use client": it asks use-intl for words (use-client.test.ts), and calls the server.
"use client";

import { useState } from "react";
import { useTranslations } from "use-intl";

import { api } from "@/api/client";
import { answerOf } from "@/api/refusal";
import { TextLink } from "@/components/design/text-link";
import { Decimal } from "@/lib/decimal";
import { formatMoney } from "@/lib/format";

import { ApproveSheet, NOTHING_STOPS, useMonthTitle } from "./approve-sheet";
import { workerPayPage, type WorkerPayMonth } from "./pay";
import { useApproval } from "./use-approval";

export function ApproveLeaver({
  answer,
  timezone,
  onDone,
  onClose,
  finalFocus,
}: {
  /** Their pay as the page shows it, and reads it again. */
  answer: WorkerPayMonth;
  timezone: string;
  /** Approved, and the page read again. */
  onDone: () => void;
  onClose: () => void;
  finalFocus: () => HTMLElement | null;
}) {
  const t = useTranslations("pay.approval");
  const monthTitle = useMonthTitle();
  // What was read, kept as the sheet opened (approve-month.tsx): on their last evening the page asks itself again each
  // minute, and a tap that comes meanwhile moves the total.
  const [read] = useState(answer);
  const { worker } = read;
  const approve = useApproval(
    (id) =>
      answerOf(
        api.POST("/api/v1/staffpay/payslips/", {
          body: {
            id,
            staff: worker.staff,
            month: answer.month,
            seen: worker.total,
          },
        }),
      ),
    onDone,
  );

  const month = monthTitle(answer.month);
  return (
    <ApproveSheet
      title={t("leaverTitle", { name: worker.display_name })}
      about={t("leaverAbout", {
        month,
        total: formatMoney(new Decimal(worker.total)),
      })}
      final={t("leaverFinal", { month })}
      stops={answer.to_approve ?? NOTHING_STOPS}
      moved={answer.worker.total !== worker.total}
      // Their pay of the earlier month, which the page moves to with its address.
      earlier={(earlier, words) => (
        <TextLink href={workerPayPage(worker.staff, earlier)}>{words}</TextLink>
      )}
      timezone={timezone}
      error={approve.error}
      busy={approve.isPending}
      onApprove={() => approve.mutate()}
      onClose={onClose}
      finalFocus={finalFocus}
    />
  );
}
