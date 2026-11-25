// approve-month.tsx — the sheet that approves a month's pay for everyone, over Mishahara (WAGE-3): how many workers and
// the whole of it, that it is for good, and what stops it (approve-sheet.tsx).
//
// It sends each worker's total as the page shows it, so whoever approves approves only what they read: a day decided a
// moment before is refused (pay_run.totals_moved), and the page behind, read again, shows the new totals, in the sheet
// too. How it is sent, and what is read again after it, is useApproval's (use-approval.ts).
//
// "use client": it asks use-intl for words (use-client.test.ts), and calls the server.
"use client";

import { useTranslations } from "use-intl";

import { api } from "@/api/client";
import { answerOf } from "@/api/refusal";
import { Button } from "@/components/design/button";
import { Decimal } from "@/lib/decimal";
import { formatMoney } from "@/lib/format";

import { ApproveSheet, NOTHING_STOPS, useMonthTitle } from "./approve-sheet";
import type { PayMonth } from "./pay";
import { useApproval } from "./use-approval";

export function ApproveMonth({
  answer,
  timezone,
  onEarlier,
  onDone,
  onClose,
  finalFocus,
}: {
  /** The month as the page shows it, and reads it again. */
  answer: PayMonth;
  timezone: string;
  /** An earlier month is to be approved first: the page moves to it, and the sheet goes with the month it was of. */
  onEarlier: (month: string) => void;
  /** Approved, and the page read again. */
  onDone: () => void;
  onClose: () => void;
  finalFocus: () => HTMLElement | null;
}) {
  const t = useTranslations("pay.approval");
  const monthTitle = useMonthTitle();
  const approve = useApproval(
    (id) =>
      answerOf(
        api.POST("/api/v1/staffpay/pay-runs/", {
          body: {
            id,
            month: answer.month,
            seen: answer.workers.map(({ staff, total }) => ({ staff, total })),
          },
        }),
      ),
    onDone,
  );

  const month = monthTitle(answer.month);
  return (
    <ApproveSheet
      title={t("monthTitle", { month })}
      about={t("monthAbout", {
        count: answer.workers.length,
        total: formatMoney(new Decimal(answer.total)),
      })}
      final={t("monthFinal", { month })}
      stops={answer.to_approve ?? NOTHING_STOPS}
      // Not a link: it would be to this very page, which keeps its month itself (useWordInAddress) and would stay.
      earlier={(earlierMonth, words) => (
        <Button
          kind="second"
          size="normal"
          onClick={() => onEarlier(earlierMonth)}
        >
          {words}
        </Button>
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
