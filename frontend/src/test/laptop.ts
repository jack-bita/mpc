// laptop.ts — the Dawa laptop's database holding the shop's people, as its sync leaves it: what the PIN
// screen's tiles read (SYNC-10). Tests only. Fake data: every name and id here is made up.
import type { components } from "@/api/schema";
import { CURSOR } from "@/offline/sync/meta";
import { shopDatabase } from "@/offline/this-shop";

import { DAWA_LAPTOP } from "./devices";
import { ASHA } from "./shop-lists";

type StaffRecord = components["schemas"]["StaffRecord"];

/** A person's staff row as the laptop keeps it: active, with a PIN, and the rest as Asha's. */
export function staffRow(
  id: string,
  fullName: string,
  displayName: string,
): StaffRecord {
  return {
    ...ASHA,
    id,
    full_name: fullName,
    display_name: displayName,
    pin_changed_at: "2026-11-01T08:00:00Z",
  };
}

/** Fills the Dawa laptop's database, through the app's own open copy (this-shop.ts), with these people,
 * as a sync at change 120 left it. It doesn't register the laptop: a test that needs it saves the device
 * itself (saveDevice), as a new device's tests must not find one. */
export async function theLaptopKnows(...people: StaffRecord[]): Promise<void> {
  const db = shopDatabase(DAWA_LAPTOP.shop.id);
  await db.staff.bulkPut(people);
  await db.meta.put({ key: CURSOR, value: 120 });
}
