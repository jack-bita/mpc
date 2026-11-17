// closures.ts — the days the shop is closed, as the server answers, in the store of server answers (ATT-9): one place,
// read by Siku duka limefungwa (closures-section.tsx) and asked again by each of its forms after a change; and a
// closure's days as the page writes them, which the list, the saved lines and Ondoa's question share; and the day before
// a day, which a moved last day may reach back to. Its own file, so the section and its forms both import it without
// importing each other, as shop-rules.ts.
//
// "use client": its useDaysOf asks use-intl for words (use-client.test.ts).
"use client";

import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "use-intl";

import { api } from "@/api/client";
import { answerOf } from "@/api/refusal";
import type { components } from "@/api/schema";
import { formatDay } from "@/lib/format";

/** One closure, as the server sends it: its days, its name, and who added it. */
export type Closure = components["schemas"]["Closure"];

/** The closures' place in the store of server answers. Apart from the rules' (SHOP_RULES): a failed read shows in the
 * closures' own section, and a change asks only them again. */
export const CLOSURES = ["shops", "closures"] as const;

/** The closures from today on, soonest first, and the shop's today, as GET /api/v1/shops/closures/ answers. */
export function useClosures() {
  return useQuery({
    queryKey: CLOSURES,
    queryFn: () => answerOf(api.GET("/api/v1/shops/closures/")),
  });
}

/** A closure's days as the page writes them: one day as one date, "09/12/2026"; a span as its first and last day,
 * "20/11/2026 – 24/11/2026", both closed. */
export function useDaysOf(): (closure: Closure) => string {
  const t = useTranslations("shopSettings.closures");
  return (closure) =>
    closure.first_day === closure.last_day
      ? formatDay(closure.first_day)
      : t("days", {
          first: formatDay(closure.first_day),
          last: formatDay(closure.last_day),
        });
}

/** The day before `day`, both as a date box writes them: "2027-01-01" → "2026-12-31". Days only, read and written in
 * UTC, so no zone, nor a clock change, moves it. */
export function dayBefore(day: string): string {
  const date = new Date(`${day}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() - 1);
  return date.toISOString().slice(0, 10);
}
