// pins.ts — the laptop the offline PIN tests start on (SYNC-10): the Dawa laptop's database with Asha
// and Baraka, each with a PIN the server set, and a quick way to save a check of a PIN. Tests only.
// Fake data: the names and PINs are the demo seed's made-up ones (backend/apps/demo/services.py).
//
// Filled the one way every test fills the laptop (laptop.ts), through the app's own open copy of the
// database, which vitest.setup.ts closes and deletes after each test.
import type { ShopDatabase } from "@/offline/db";
import { rememberPin } from "@/offline/pin";
import { shopDatabase } from "@/offline/this-shop";

import { DAWA_LAPTOP } from "./devices";
import { PIN_SET_AT, staffRow, theLaptopKnows } from "./laptop";
import { ASHA } from "./shop-lists";

export { PIN_SET_AT };

/** A later time: a manager gave a new PIN. */
export const PIN_CHANGED_AT = "2026-11-12T09:30:00Z";

export const ASHA_PIN = "2580";
export const BARAKA_PIN = "1470";

/** Asha's staff row on the laptop, with her PIN's time. */
export const ASHA_ROW = staffRow(ASHA.id, ASHA.full_name, ASHA.display_name);

/** Baraka's: another person of the same shop, with a PIN of his own. */
export const BARAKA_ROW = staffRow(
  "019a5e00-0000-7000-8000-0000000000c3",
  "Baraka Mfano",
  "Baraka",
);

/** A few turns of the blender, so a check costs a test a moment, not 0.3 s. The real number has a test
 * of its own (pin.check.test.ts), and a check is always read with the turns saved in it. */
export const FEW_TURNS = 1_000;

/** 08:00 in the shop, on the laptop's clock: the tests move time on from here by hand. */
export const EIGHT_AM = Date.parse("2026-11-12T05:00:00Z");

/** The Dawa laptop, filled at change 120 with Asha and Baraka, as a bootstrap leaves it. */
export async function laptopWithStaff(): Promise<ShopDatabase> {
  await theLaptopKnows(ASHA_ROW, BARAKA_ROW);
  return shopDatabase(DAWA_LAPTOP.shop.id);
}

/** Asha's online login: the server said yes to 2580, and the laptop saved its check of it. */
export function ashaLoggedInOnline(db: ShopDatabase): Promise<void> {
  return rememberPin(db, ASHA_ROW.id, ASHA_PIN, FEW_TURNS);
}
