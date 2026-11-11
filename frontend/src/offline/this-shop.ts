// this-shop.ts — the database of the shop this device belongs to, one open copy per shop for the whole
// app (SYNC-7, 03 §6.1).
//
// Which shop comes from the device's saved copy (mpc.device, this-device.ts), never from the server:
// counter screens read the database with no network, and the shop must be known before its database can
// be opened. Opened once and shared: every screen and the sync then see the same connection, and Dexie
// tells each live query of a change made through any of them.
import { useThisDevice } from "@/features/devices/this-device";

import { openShopDatabase, type ShopDatabase } from "./db";

const opened = new Map<string, ShopDatabase>();

/** The shop's database, opened the first time it is asked for. */
export function shopDatabase(shopId: string): ShopDatabase {
  let db = opened.get(shopId);
  if (db === undefined) {
    db = openShopDatabase(shopId);
    opened.set(shopId, db);
  }
  return db;
}

/** This device's shop database, or null while the device isn't registered: no shop, so no data. */
export function useShopDatabase(): ShopDatabase | null {
  const shopId = useThisDevice()?.shop.id;
  return shopId === undefined ? null : shopDatabase(shopId);
}

/** Closes and forgets every open database. Tests only, so each starts on a laptop with none open. */
export function closeShopDatabases(): void {
  for (const db of opened.values()) db.close();
  opened.clear();
}
