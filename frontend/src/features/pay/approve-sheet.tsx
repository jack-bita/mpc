// approve-sheet.tsx — Idhinisha: a month's pay approved, or one worker's alone, in a sheet over its own page, as Jack
// pictured it (WAGE-3, 25 Nov 2026):
//
//   ┌──────────────────────────────────┐
//   │ Idhinisha Novemba 2026           │
//   │ Watu 3 · Jumla TSh 432,000       │
//   │ Baada ya kuidhinisha, Novemba    │
//   │ 2026 haibadiliki tena.           │
//   │ ! Laptop ya Vyakula haijatuma    │  what it warns of, which stops nothing (Jack: A)
//   │   tangu 28/11/2026               │
//   │ [ Ghairi ]         [ Idhinisha ] │
//   └──────────────────────────────────┘
//
// Or, while something stops it, what does in place of that sentence, each opening where it is mended, and Idhinisha
// held: an earlier month, "Amua siku hii kwanza: Juma · Alhamisi 12/11" (Jack: A), a day with no daily pay, or a worker
// still clocked in. The server says what stops it (ToApprove) and asks it all again as it approves; its refusals show
// above the buttons. Approving is for good (A3), so the sheet says so before the tap.
//
// The screen gives what is approved and sends it; this part is what both sheets show alike.
//
// "use client": it asks use-intl for words (use-client.test.ts).
"use client";

import type { ReactNode } from "react";
import { useTranslations } from "use-intl";

import { aboutTheWholeRequest } from "@/api/refusal";
import { ApiErrorAlert } from "@/components/api-error-alert";
import { Sheet } from "@/components/design/sheet";
import { TextLink } from "@/components/design/text-link";
import {
  monthOf,
  type MonthNumber,
  type Weekday,
} from "@/features/attendance/attendance-month";
import { workerMonthAddress } from "@/features/attendance/worker-month";
import { workerPage } from "@/features/workers/workers";
import { formatDate, formatDayMonth, weekdayOf } from "@/lib/format";
import { useOnline } from "@/offline/network";

import type { OpenDay, ToApprove } from "./pay";

/** Nothing stops it, and nothing to warn of: what a sheet shows in the moment its page learns it was approved, before
 * the sheet goes. */
export const NOTHING_STOPS: ToApprove = {
  earlier: null,
  waiting: [],
  no_rate: [],
  still_clocked_in: false,
  quiet_laptops: [],
  came_unpaid: [],
};

/** Whether anything stops the approval. */
function isStopped(stops: ToApprove): boolean {
  return (
    stops.earlier !== null ||
    stops.still_clocked_in ||
    stops.waiting.length > 0 ||
    stops.no_rate.length > 0
  );
}

/** "Novemba 2026", a month in words. */
export function useMonthTitle(): (month: string) => string {
  const monthWords = useTranslations("attendanceMonth");
  return (month) => {
    const [year, number] = month.split("-") as [string, MonthNumber];
    return monthWords("monthTitle", {
      month: monthWords(`monthNames.${number}`),
      year,
    });
  };
}

export function ApproveSheet({
  title,
  about,
  final,
  stops,
  earlier,
  timezone,
  error,
  busy,
  onApprove,
  onClose,
  finalFocus,
}: {
  title: string;
  /** How many and how much, under the title. */
  about: string;
  /** That it is for good, in the words of what is approved. */
  final: string;
  stops: ToApprove;
  /** What opens an earlier month, "Oktoba 2026", which is approved first: a link, or the page's own move to it. */
  earlier: (month: string, words: string) => ReactNode;
  /** The shop's, for when a laptop last sent. */
  timezone: string;
  /** Why the last try failed, if it did. */
  error: Error | null;
  busy: boolean;
  onApprove: () => void;
  /** Ghairi or Esc. */
  onClose: () => void;
  /** Where the keyboard goes as the sheet goes (sheet.tsx). */
  finalFocus: () => HTMLElement | null;
}) {
  const t = useTranslations("pay.approval");
  const online = useOnline();
  const monthTitle = useMonthTitle();
  return (
    <Sheet
      open
      onClose={onClose}
      title={title}
      description={about}
      actionLabel={t("action")}
      onAction={onApprove}
      busy={busy}
      // Offline, nothing is sent, so nothing waits unsent while it looks done; and while something stops it, there is
      // nothing to send: the server would only refuse it.
      actionDisabled={!online || isStopped(stops)}
      finalFocus={finalFocus}
    >
      {stops.earlier !== null ? (
        <div className="flex flex-wrap items-center gap-2">
          <p>{t("earlier")}</p>
          {earlier(stops.earlier, monthTitle(stops.earlier))}
        </div>
      ) : null}
      {stops.still_clocked_in ? <p>{t("stillClockedIn")}</p> : null}
      {/* A day that waits opens where it is decided (ATT-12); a day with no daily pay, the worker's page, where one is
          typed (Malipo kwa siku). */}
      <Days
        title={t("waiting", { count: stops.waiting.length })}
        days={stops.waiting}
        opens={(day) =>
          workerMonthAddress(day.staff, monthOf(day.date), day.date)
        }
      />
      <Days
        title={t("noRate", { count: stops.no_rate.length })}
        days={stops.no_rate}
        opens={(day) => workerPage(day.staff)}
      />
      {isStopped(stops) ? null : <p>{final}</p>}
      {stops.quiet_laptops.map((laptop) => (
        <Warning key={laptop.name}>
          {laptop.last_synced_at === null
            ? t("laptopNever", { name: laptop.name })
            : t("laptopQuiet", {
                name: laptop.name,
                date: formatDate(laptop.last_synced_at, timezone),
              })}
        </Warning>
      ))}
      {stops.came_unpaid.map((name) => (
        <Warning key={name}>{t("cameUnpaid", { name })}</Warning>
      ))}
      {/* What the server refused: a total that moved, a day decided otherwise meanwhile, a key taken away, no network. */}
      <ApiErrorAlert error={aboutTheWholeRequest(error)} />
    </Sheet>
  );
}

/** "Amua siku hii kwanza:" and the days, each a link to where it is mended. Nothing for none. */
function Days({
  title,
  days,
  opens,
}: {
  title: string;
  days: OpenDay[];
  opens: (day: OpenDay) => string;
}) {
  const t = useTranslations("pay.approval");
  const monthWords = useTranslations("attendanceMonth");
  if (days.length === 0) return null;
  return (
    <div className="grid gap-1">
      <p>{title}</p>
      {/* role="list" written out: Safari with VoiceOver stops calling a styled <ul> a list (workers-screen.tsx). */}
      <ul role="list" aria-label={title} className="grid gap-1">
        {days.map((day) => (
          <li key={`${day.staff} ${day.date}`}>
            <TextLink href={opens(day)}>
              {t("day", {
                name: day.display_name,
                weekday: monthWords(
                  `weekdays.${String(weekdayOf(day.date)) as Weekday}`,
                ),
                date: formatDayMonth(day.date),
              })}
            </TextLink>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Something to look at before the tap, which stops nothing, with the ! of a day to decide. */
function Warning({ children }: { children: ReactNode }) {
  const monthWords = useTranslations("attendanceMonth");
  return (
    <p className="text-muted-foreground">
      {/* The mark for the eye: the words say it to a screen reader. */}
      <span aria-hidden className="font-semibold">
        {monthWords("mark.needs_review")}{" "}
      </span>
      {children}
    </p>
  );
}
