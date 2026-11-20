// closures.ts — the days the shop is closed, as the server answers, in the store of server answers (ATT-9): one place,
// read by Siku duka limefungwa (closures-section.tsx) and asked again by each of its forms after a change; and a
// closure's days as the page writes them, which the list, the saved lines and Ondoa's question share. The day before a
// day, which a moved last day may reach back to, is a day's own sum, in src/lib/format.ts with the rest (ATT-5). Its own
// file, so the section and its forms both import it without
// importing each other, as shop-rules.ts.
//
// A change puts the server's answer into the list at once (keepClosure, dropClosure), as sides.ts does for a side, and
// then the list is read again: until that answer comes, or if it never does, as the network drops right after, the page
// already shows what the server said. A cancelled closure never stays on the page with its buttons (ATT-9's review).
//
// "use client": its useDaysOf asks use-intl for words (use-client.test.ts).
"use client";

import { type QueryClient, useQuery } from "@tanstack/react-query";
import { useTranslations } from "use-intl";

import { api } from "@/api/client";
import { answerOf, ApiRefusal } from "@/api/refusal";
import type { components } from "@/api/schema";
import { formatDay } from "@/lib/format";

/** One closure, as the server sends it: its days, its name, and who added it. */
export type Closure = components["schemas"]["Closure"];

/** The list as GET /api/v1/shops/closures/ answers it. */
type ClosuresAnswer = components["schemas"]["ShopClosuresAnswer"];

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

/** Puts a closure as the server saved it into the list at once: in its place, soonest first, as the server orders them
 * (coming_closures: by first day, then id); or out of it, once it ends before the shop's today, as the server lists
 * none already over. A new one goes in, a changed one replaces its old copy. */
export function keepClosure(store: QueryClient, saved: Closure): void {
  store.setQueryData<ClosuresAnswer>(CLOSURES, (list) => {
    if (!list) return list;
    const others = list.closures.filter((each) => each.id !== saved.id);
    if (saved.last_day < list.today) return { ...list, closures: others };
    return {
      ...list,
      closures: [...others, saved].sort(
        (one, other) =>
          one.first_day.localeCompare(other.first_day) ||
          one.id.localeCompare(other.id),
      ),
    };
  });
}

/** Takes a closure out of the list at once: it was cancelled, by this page or by someone else. */
export function dropClosure(store: QueryClient, id: string): void {
  store.setQueryData<ClosuresAnswer>(
    CLOSURES,
    (list) =>
      list && {
        ...list,
        closures: list.closures.filter((each) => each.id !== id),
      },
  );
}

/** What a form shows above its buttons, ApiErrorAlert's: the failure, unless it is a refusal about its fields only. The
 * server names the first problem with the whole request as the refusal's code, and puts the fields' codes beside it,
 * calling a refusal of fields alone `invalid` (apps/core/api/errors.py). So a clash with a demo's refusal of today
 * comes as `closure.overlaps` with `first_day` beside it: the form says both at once, not the clash on the next try
 * (ATT-9's review). */
export function aboutTheWholeRequest(error: unknown): unknown {
  return error instanceof ApiRefusal &&
    error.body.code === "invalid" &&
    Object.keys(error.body.fields).length > 0
    ? null
    : error;
}
