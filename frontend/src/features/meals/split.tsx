// split.tsx — how one day's meal money is split, in words, under its amount on the list and on the day's own page
// (WAGE-7): "Watu 8 · TSh 1,000 kila mmoja", "1 anasubiri uamuzi".
//
// "use client": it asks use-intl for words (use-client.test.ts).
"use client";

import { useTranslations } from "use-intl";

import { Decimal } from "@/lib/decimal";
import { formatMoney } from "@/lib/format";

import type { MealDay } from "./meal-money";

/** How a day's money is split: not yet, today; among how many, and each one's share; and how many wait. */
export function Split({ day }: { day: MealDay }) {
  const t = useTranslations("mealMoney");
  const said = [
    !day.over
      ? t("notSplitYet")
      : day.sharers > 0
        ? t("split", {
            count: day.sharers,
            share: formatMoney(new Decimal(day.share)),
          })
        : day.waiting > 0
          ? // Nobody shares it yet, but someone may: only who waits is said, below.
            null
          : t("nobodyShares"),
    day.waiting > 0 ? t("waiting", { count: day.waiting }) : null,
  ].filter((each) => each !== null);
  return said.map((each) => (
    <p key={each} className="col-span-2 text-muted-foreground">
      {each}
    </p>
  ));
}
