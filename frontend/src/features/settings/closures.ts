// closures.ts — the days the shop is closed, as the server answers, in the store of server answers (ATT-9): one place,
// read by Siku duka limefungwa (closures-section.tsx) and asked again by each of its forms after a change. Its own
// file, so the section and its forms both import it without importing each other, as shop-rules.ts.
import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import { answerOf } from "@/api/refusal";
import type { components } from "@/api/schema";

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
