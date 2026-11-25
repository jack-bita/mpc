// choose-days.tsx — Chagua siku: the days Hela ya chakula shows, with the whole of their money, chosen in a sheet over the
// list (WAGE-7), as Jack asked for it (24 Nov 2026), and as nothing opens in place on a page (CTRL-4):
//
//   ┌──────────────────────────────────┐
//   │ Chagua siku                      │
//   │ Kuanzia         [ 20/11/2026 ]   │
//   │ Hadi            [ 23/11/2026 ]   │
//   │ [ Ghairi ]           [ Onyesha ] │
//   └──────────────────────────────────┘
//
// The same date in both is one day. It starts on the days the list shows. What the sheet can see is wrong is said at
// once beside its box, in the server's own sentences, and nothing is asked: an empty box, a day to come, Hadi before
// Kuanzia, more than a year, or no shop's day, as a year typed "26". The screen keeps the days, in its address, and this
// sheet only picks them: Ghairi leaves the list as it was. The way back to the month is Mwezi mzima, on the page beside
// the days chosen, as Tofauti's Onyesha zote is, so every sheet keeps its Ghairi.
//
// "use client": it asks use-intl for words (use-client.test.ts), and keeps what is picked.
"use client";

import { useState } from "react";
import { useTranslations } from "use-intl";

import { Field } from "@/components/design/field";
import { Sheet } from "@/components/design/sheet";
import { codeMessage, useCodeWords } from "@/i18n/codes";

import { isDay, isTooLong, type Span } from "./meal-money";

/** A day no shop has, as a year typed "26", which the box keeps as 0026: the sheet's own word, as it asks nothing. */
const NOT_A_DAY = "not_a_day";

/** The form's own checks, by box, as the codes the server would send, or the sheet's own one. */
type Checks = { first?: string; last?: string };

/** What is wrong with one box's day by itself, if anything. Days as text sort as days do. */
function problemOf(day: string, today: string): string | undefined {
  if (day === "") return "required";
  if (!isDay(day)) return NOT_A_DAY;
  return day > today ? "meal_money.in_future" : undefined;
}

/** What is wrong with the two days, if anything: each box's first problem, then the two together, beside Hadi, only once
 * each holds a day. */
function checksOf({ first, last }: Span, today: string): Checks {
  const checks: Checks = {
    first: problemOf(first, today),
    last: problemOf(last, today),
  };
  if (checks.first === undefined && checks.last === undefined) {
    if (last < first) checks.last = "meal_money.days_backwards";
    else if (isTooLong({ first, last }))
      checks.last = "meal_money.too_many_days";
  }
  return checks;
}

export function ChooseDaysSheet({
  span,
  today,
  onShow,
  onClose,
  finalFocus,
}: {
  /** The days the list shows, picked as the sheet opens. */
  span: Span;
  /** The shop's today: no day after it has any meals yet. */
  today: string;
  /** Onyesha: the list kept to these. */
  onShow: (span: Span) => void;
  onClose: () => void;
  /** Where the keyboard goes as it closes: Chagua siku's button. */
  finalFocus: () => HTMLElement | null;
}) {
  const t = useTranslations("mealMoney.choose");
  const codes = useCodeWords();
  const [first, setFirst] = useState(span.first);
  // A month that isn't over ends today, not on its last day, which hasn't come.
  const [last, setLast] = useState(span.last > today ? today : span.last);
  const [own, setOwn] = useState<Checks>({});
  const said = (code?: string) =>
    code === undefined
      ? undefined
      : code === NOT_A_DAY
        ? t("notADay")
        : codeMessage(codes, code);

  return (
    <Sheet
      open
      onClose={onClose}
      title={t("title")}
      actionLabel={t("show")}
      finalFocus={finalFocus}
      onAction={() => {
        const checks = checksOf({ first, last }, today);
        setOwn(checks);
        if (checks.first === undefined && checks.last === undefined)
          onShow({ first, last });
      }}
    >
      <Field
        label={t("first")}
        error={said(own.first)}
        type="date"
        // The phone's calendar offers no day to come.
        max={today}
        value={first}
        onChange={(event) => setFirst(event.target.value)}
      />
      <Field
        label={t("last")}
        error={said(own.last)}
        type="date"
        max={today}
        value={last}
        onChange={(event) => setLast(event.target.value)}
      />
    </Sheet>
  );
}
