// sides.ts — the shop's sides on Mipangilio ya duka, in the store of server answers: where the list is kept, and how a
// side's change puts the server's answer there (SHOP-5, SHOP-4). Shared by Pande's switch (side-switch.tsx) and its
// band (side-band-choice.tsx), which each change one side through PATCH /api/v1/shops/sides/{id}/.
import type { QueryClient } from "@tanstack/react-query";

import type { components } from "@/api/schema";

type Side = components["schemas"]["Side"];

/** The sides' place in the store of server answers. */
export const SIDES = ["shops", "sides"] as const;

/** Puts a side as the server answered a change into the list at once, with its new version, so the next change of
 * that side sends that one, and every part of the page shows it. */
export function keepTheSide(store: QueryClient, saved: Side): void {
  store.setQueryData<components["schemas"]["PaginatedSideList"]>(
    SIDES,
    (page) =>
      page && {
        ...page,
        results: page.results.map((each) =>
          each.id === saved.id ? saved : each,
        ),
      },
  );
}
