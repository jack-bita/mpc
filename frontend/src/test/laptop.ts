// laptop.ts — the Dawa laptop's database holding the shop's people, as its sync leaves it: what the PIN
// screen's tiles read (SYNC-10); and the attendance switch's row, which the welcome and Mahudhurio read
// (ATT-2). Tests only. Fake data: every name and id here is made up.
import type { components } from "@/api/schema";
import { CURSOR } from "@/offline/sync/meta";
import { shopDatabase } from "@/offline/this-shop";

import { DAWA_LAPTOP } from "./devices";
import { ASHA } from "./shop-lists";

type StaffRecord = components["schemas"]["StaffRecord"];

/** When the server set every test person's PIN. */
export const PIN_SET_AT = "2026-11-01T08:00:00Z";

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
    pin_changed_at: PIN_SET_AT,
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

/** The shop switched attendance on from `from` on (ATT-2), as a pull leaves the switch's row on the Dawa
 * laptop: its row only, as the app carries the switch's kind and default (attendance-on.ts). Each call
 * writes the same row, so a later call moves the day. */
export async function attendanceSwitchedOn(from = "2026-11-01"): Promise<void> {
  await shopDatabase(DAWA_LAPTOP.shop.id).setting.put({
    id: "019a5e00-0000-7000-8000-00000000a7e1",
    key: "attendance.enabled",
    side: null,
    value: "true",
    effective_from: from,
  });
}
