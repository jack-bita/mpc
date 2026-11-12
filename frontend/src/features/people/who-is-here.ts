// who-is-here.ts — who is logged in, at which shop, and what they may do on each side, as the office
// screens ask it (UI-3, 03 §5.10).
//
// GET /api/auth/me/ answers for the session this browser holds: a password's on a manager's own phone,
// or a PIN's at a shop device (AUTH-4). A screen reads it to offer only what the person may do: the
// devices screen offers Sajili kifaa only on the sides where they hold device.manage. The server still
// checks every change itself (PPL-5); this only keeps a button nobody may press off the screen.
//
// One place in the store of server answers, so every office screen shares one answer. UI-4 and UI-5,
// which log people in and out, empty the store then (forgetTheLastPerson, src/api/query-client.ts), so
// the next person never reads the last one's keys.
import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import { answerOf } from "@/api/refusal";
import type { components } from "@/api/schema";

export type WhoIsHere = components["schemas"]["WhoIsHere"];
export type SideKeys = components["schemas"]["MeSideKeys"];
type StaffRecord = components["schemas"]["StaffRecord"];
type SideRecord = components["schemas"]["SideRecord"];

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

/** The side a person works on at this device, for the top bar (UI-4): the device's home side if they
 * hold a key there, or else the first side they hold one on; none if they hold none. */
export function sideAt(
  me: WhoIsHere,
  homeSideId: string,
): SideKeys | undefined {
  const sides = me.permissions.sides;
  // A Vyakula seller at the Dawa laptop sells Vyakula's goods: the bar says where she works, so nobody
  // has to guess which side a sale will go to.
  return sides.find((side) => side.id === homeSideId) ?? sides[0];
}

/**
 * The same for someone logged in offline (SYNC-10), who has no `me`: from their staff row on the laptop
 * and the laptop's sides. A key on the whole shop holds on every side, as the server counts it for `me`.
 */
export function sideOfStaffRow(
  row: StaffRecord,
  homeSideId: string,
  sides: SideRecord[],
): SideRecord | undefined {
  const held =
    row.permissions.every_side.length > 0
      ? sides.map((side) => side.id)
      : row.permissions.sides
          .filter((keys) => keys.permissions.length > 0)
          .map((keys) => keys.side);
  const id = held.includes(homeSideId) ? homeSideId : held[0];
  return sides.find((side) => side.id === id);
}
