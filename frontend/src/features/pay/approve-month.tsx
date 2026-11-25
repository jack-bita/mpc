// approve-month.tsx — the sheet that approves a month's pay for everyone, over Mishahara (WAGE-3): how many workers and
// the whole of it, that it is for good, and what stops it (approve-sheet.tsx).
//
// It sends each worker's total as the page showed it when the sheet opened, so whoever approves approves only what they
// read: a day decided meanwhile, which the page behind learns as it is read again, moves a total, and the sheet says so
// and holds its button until it is closed and the page read (WAGE-3's review). The server refuses the same
// (pay_run.totals_moved). How it is sent, and what is read again after it, is useApproval's (use-approval.ts).
//
// "use client": it asks use-intl for words (use-client.test.ts), and calls the server.
"use client";

import { useState } from "react";
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
  // What was read, kept as the sheet opened: a second tap would otherwise approve totals that came under it.
  const [read] = useState(answer);
  const approve = useApproval(
    (id) =>
      answerOf(
        api.POST("/api/v1/staffpay/pay-runs/", {
          body: {
            id,
            month: answer.month,
            seen: read.workers.map(({ staff, total }) => ({ staff, total })),
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
        count: read.workers.length,
        total: formatMoney(new Decimal(read.total)),
      })}
      final={t("monthFinal", { month })}
      stops={answer.to_approve ?? NOTHING_STOPS}
      moved={totalsOf(answer) !== totalsOf(read)}
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

/** Each worker's total, whole, to see whether any has moved: never the whole month's alone, as two changes could cancel
 * each other out. In the server's order, by name, as both answers are. */
function totalsOf(month: PayMonth): string {
  return month.workers.map(({ staff, total }) => `${staff} ${total}`).join();
}
