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
// Kuanzia, more than a year. The screen keeps the days, in its address, and this sheet only picks them: Ghairi leaves
// the list as it was. The way back to the month is Mwezi mzima, on the page beside the days chosen, as Tofauti's
// Onyesha zote is, so every sheet keeps its Ghairi.
//
// "use client": it asks use-intl for words (use-client.test.ts), and keeps what is picked.
"use client";

import { useState } from "react";
import { useTranslations } from "use-intl";

import { Field } from "@/components/design/field";
import { Sheet } from "@/components/design/sheet";
import { codeMessage, useCodeWords } from "@/i18n/codes";

import { isTooLong, type Span } from "./meal-money";

/** The form's own checks, by box, as the codes the server would send. */
type Checks = { first?: string; last?: string };

/** What is wrong with the two days, if anything: each box's first problem. Days as text sort as days do. */
function checksOf({ first, last }: Span, today: string): Checks {
  const checks: Checks = {};
  if (first === "") checks.first = "required";
  else if (first > today) checks.first = "meal_money.in_future";
  if (last === "") checks.last = "required";
  else if (last > today) checks.last = "meal_money.in_future";
  // Only once both hold a day: an empty box is said once, beside itself.
  else if (first !== "" && last < first)
    checks.last = "meal_money.days_backwards";
  else if (first !== "" && isTooLong({ first, last }))
    checks.last = "meal_money.too_many_days";
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
    code === undefined ? undefined : codeMessage(codes, code);

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
