// approved-line.tsx — "Imeidhinishwa na Baba · 1/12/2026 19:05 usiku": who approved a month's pay, or one worker's alone,
// and when, on Mishahara and on a worker's pay (WAGE-3). On the shop's own clock and calendar, as every time of day is
// (Jack, SYNC-11).
//
// "use client": it asks use-intl for words (use-client.test.ts).
"use client";

import { useTranslations } from "use-intl";

import { dayPart, formatDate, formatTime } from "@/lib/format";

import type { Approval } from "./pay";

export function ApprovedLine({
  approval,
  timezone,
}: {
  approval: Approval;
  timezone: string;
}) {
  const t = useTranslations("pay.approval");
  const attendance = useTranslations("attendance");
  return (
    <p>
      {t("approvedBy", {
        by: approval.by,
        date: formatDate(approval.at, timezone),
        time: attendance("timeOfDay", {
          time: formatTime(approval.at, timezone),
          part: dayPart(approval.at, timezone),
        }),
      })}
    </p>
  );
}
