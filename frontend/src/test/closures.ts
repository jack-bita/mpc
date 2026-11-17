// closures.ts — made-up answers of GET /api/v1/shops/closures/ for the tests of Siku duka limefungwa (ATT-9): a
// builder for one closure, and the list the page reads. Tests only. Fake data: public holidays, and a made-up family
// funeral, on the shop's today of settings.ts.
import type { components } from "@/api/schema";

import { TODAY } from "./settings";

type Closure = components["schemas"]["Closure"];

let closures = 0;

/** A closure, the funeral of the card's example unless told otherwise (20–24 Nov 2026), added by Neema. Each its own
 * id. */
export function closure(fields: Partial<Closure> = {}): Closure {
  closures += 1;
  return {
    id: `019a8200-0000-7000-8000-${String(closures).padStart(12, "0")}`,
    first_day: "2026-11-20",
    last_day: "2026-11-24",
    name: "Msiba wa bibi",
    status: "active",
    added_by: "Neema",
    created_at: "2026-11-15T07:00:00Z",
    ...fields,
  };
}

/** The answer of the list: the closures as given, in the server's order, and the shop's today. */
export function closuresAnswer(
  list: Closure[] = [],
): components["schemas"]["ShopClosuresAnswer"] {
  return { today: TODAY, closures: list };
}
