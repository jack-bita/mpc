// shop-rules.ts — the shop's rules as the server answers, in the store of server answers (SHOP-5): one place,
// read by the settings page and asked again by its form after a save. Its own file, so the page and the form
// both import it without importing each other.
import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import { answerOf } from "@/api/refusal";

/** The rules' place in the store of server answers. */
export const SHOP_RULES = ["shops", "settings"] as const;

/** Every rule, with its value today and its rows, as GET /api/v1/shops/settings/ answers. */
export function useShopRules() {
  return useQuery({
    queryKey: SHOP_RULES,
    queryFn: () => answerOf(api.GET("/api/v1/shops/settings/")),
  });
}
