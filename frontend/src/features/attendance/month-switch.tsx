// month-switch.tsx — ‹ Novemba 2026 ›, the month a page shows and the two arrows that move it, and the clock that page
// keeps, so › stops at this month (ATT-5). Mahudhurio ya mwezi wears it, Hela ya chakula (WAGE-7), Mishahara, the month's
// pay on a worker's page (WAGE-2), and Advansi (WAGE-8): one switch, so they all move a month the same way.
//
// "use client": it asks use-intl for words (use-client.test.ts), and keeps the page's clock.
"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslations } from "use-intl";

import { Button } from "@/components/design/button";

import { monthAfter, monthBefore, type MonthNumber } from "./attendance-month";

/** The page's two looks at the clock: the moment it opened, kept; and the last, as it opened, then each time it comes
 * back into view. Baba leaves November open on 30 November and unlocks his phone on 2 December: the store asks for
 * November again as the page comes back (TanStack's refetch on focus), November stays on show, and this month moves
 * on, so › reaches December (the review). */
export function usePagesClock(): { openedAt: number; now: number } {
  const [openedAt] = useState(() => Date.now());
  const [now, setNow] = useState(openedAt);
  useEffect(() => {
    function lookAgain() {
      if (document.visibilityState !== "hidden") setNow(Date.now());
    }
    // A phone unlocked, or a tab come back to, says it is visible again; a laptop's window clicked into, focused.
    document.addEventListener("visibilitychange", lookAgain);
    window.addEventListener("focus", lookAgain);
    return () => {
      document.removeEventListener("visibilitychange", lookAgain);
      window.removeEventListener("focus", lookAgain);
    };
  }, []);
  return { openedAt, now };
}

/** ‹ Novemba 2026 ›: the month's name between its two arrows, › only before this month. */
export function MonthSwitch({
  month,
  thisMonth,
  onChoose,
  heading: Heading = "h2",
}: {
  month: string;
  thisMonth: string;
  onChoose: (month: string) => void;
  /** The month's heading: under a card's own (h2), an h3, so a screen reader's list of headings nests as the page does
   * (a worker's page, WAGE-2). */
  heading?: "h2" | "h3";
}) {
  const t = useTranslations("attendanceMonth");
  const [year, number] = month.split("-") as [string, string];
  return (
    // Three columns, the name always in the middle. Each arrow a square button as tall as
    // a normal one, so a finger finds it; its name a word, as a screen reader can't read an arrow (page-header.tsx).
    <nav
      aria-label={t("months")}
      className="grid grid-cols-[auto_1fr_auto] items-center gap-3"
    >
      <Button
        kind="second"
        size="normal"
        aria-label={t("before")}
        className="w-(--control-normal) px-0"
        onClick={() => onChoose(monthBefore(month))}
      >
        <ChevronLeft aria-hidden className="size-6" />
      </Button>
      {/* A heading, so a screen reader can jump to it, and says the month as it changes: the page's title stays. */}
      <Heading aria-live="polite" className="text-center text-xl font-semibold">
        {t("monthTitle", {
          month: t(`monthNames.${number as MonthNumber}`),
          year,
        })}
      </Heading>
      {/* Always there, greyed out on this month, as no day after today is over. Never taken away: pressed to reach
          this month, a button that went would take the keyboard's place with it, back to the page's top (the review).
          focusableWhenDisabled keeps it in the Tab order, said "dimmed" by a screen reader, where a plain disabled
          button would drop the focus it has. */}
      <Button
        kind="second"
        size="normal"
        aria-label={t("after")}
        className="w-(--control-normal) px-0"
        disabled={month >= thisMonth}
        focusableWhenDisabled
        onClick={() => onChoose(monthAfter(month))}
      >
        <ChevronRight aria-hidden className="size-6" />
      </Button>
    </nav>
  );
}
