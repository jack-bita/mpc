// approve-month.tsx — the sheet that approves a month's pay for everyone, over Mishahara (WAGE-3): how many workers and
// the whole of it, that it is for good, and what stops it (approve-sheet.tsx).
//
// It sends each worker's total as the page shows it, so whoever approves approves only what they read: a day decided a
// moment before is refused (pay_run.totals_moved), and the page behind, read again, shows the new totals, in the sheet
// too. Its id is made once, as it opens: a try whose answer was lost on the way, sent again, is the same approval
// (ADR-0007). Once approved, it waits for the page to be read again before it closes, so it never closes onto a month
// that still looks open; and every page the approval locks is asked again: the attendance, the meal money, the advances.
//
// "use client": it asks use-intl for words (use-client.test.ts), and calls the server.
"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslations } from "use-intl";

import { api } from "@/api/client";
import { answerOf } from "@/api/refusal";
import { Button } from "@/components/design/button";
import { Decimal } from "@/lib/decimal";
import { formatMoney } from "@/lib/format";
import { newId } from "@/lib/ids";

import { ApproveSheet, NOTHING_STOPS, useMonthTitle } from "./approve-sheet";
import { type PayMonth, whatAnApprovalLocks } from "./pay";

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
  const store = useQueryClient();
  const monthTitle = useMonthTitle();
  const [id] = useState(newId);

  const askAgain = () =>
    Promise.all(
      whatAnApprovalLocks().map((queryKey) =>
        store.invalidateQueries({ queryKey }),
      ),
    );
  const approve = useMutation({
    mutationFn: () =>
      answerOf(
        api.POST("/api/v1/staffpay/pay-runs/", {
          body: {
            id,
            month: answer.month,
            seen: answer.workers.map(({ staff, total }) => ({ staff, total })),
          },
        }),
      ),
    onSuccess: async () => {
      await askAgain();
      onDone();
    },
    onError: () => {
      // Asked again too: refused because a total moved, the new ones show; and with no answer, it may have been approved
      // all the same.
      void askAgain();
    },
  });

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
