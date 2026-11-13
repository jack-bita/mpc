// side-of-row.ts — which side the top bar names for someone at a device, worked out from the laptop's own copy:
// their staff row and the shop's sides (SYNC-10, SYNC-11). The same answer `me` gives (sideAt, who-is-here.ts),
// with no server.
//
// A file of its own, apart from who-is-here.ts, which asks the server: the counter's frame needs this, and a
// counter screen must never import a part that brings the API client with it (rule 5, ADR-0019), as the
// counter's lint rule reads only the screen's own code and would not see it (SYNC-11's review).
import type { components } from "@/api/schema";

type StaffRecord = components["schemas"]["StaffRecord"];
type SideRecord = components["schemas"]["SideRecord"];

/**
 * The side a person works on at this device, for the top bar, from their staff row on the laptop and the
 * laptop's sides: someone logged in offline (SYNC-10), who has no `me`, and anyone at the counter
 * (SYNC-11). A key on the whole shop holds on every side, as the server counts it for `me`.
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
