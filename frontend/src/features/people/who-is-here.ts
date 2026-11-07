// who-is-here.ts — who is logged in, at which shop, and what they may do on each side, as the office
// screens ask it (UI-3, 03 §5.10).
//
// GET /api/auth/me/ answers for the session this browser holds: a password's on a manager's own phone,
// or a PIN's at a shop device (AUTH-4). A screen reads it to offer only what the person may do: the
// devices screen offers Sajili kifaa only on the sides where they hold device.manage. The server still
// checks every change itself (PPL-5); this only keeps a button nobody may press off the screen.
//
// One place in the store of server answers, so every office screen shares one answer. UI-4 and UI-5,
// which log people in and out, clear the store then, so the next person never reads the last one's keys.
import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import { answerOf } from "@/api/refusal";
import type { components } from "@/api/schema";

export type WhoIsHere = components["schemas"]["WhoIsHere"];
export type SideKeys = components["schemas"]["MeSideKeys"];

/** The answer's place in the store of server answers. */
export const WHO_IS_HERE = ["auth", "me"] as const;

/** Who is logged in here. Not logged in, it fails with 403 not_authenticated, which ApiErrorAlert says
 * as "Ingia kwanza". */
export function useWhoIsHere() {
  return useQuery({
    queryKey: WHO_IS_HERE,
    queryFn: () => answerOf(api.GET("/api/auth/me/")),
  });
}

/** The sides where the person holds `key`, in the server's order. A key on the whole shop is already
 * counted on every side (HeldPermissions.on, backend/apps/core/permissions.py). */
export function sidesWhere(me: WhoIsHere, key: string): SideKeys[] {
  return me.permissions.sides.filter((side) => side.permissions.includes(key));
}
