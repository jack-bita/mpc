// page-place.ts — the page's place for a sync (place.ts): the app's own client, and a refusal of the
// device kept in localStorage, as the device check keeps it (this-device.ts, 03 §5.9).
//
// Kept apart from push.ts and answer.ts so the service worker, which bundles those, never pulls in the
// page's device copy, React's hooks and all, nor reaches for a `window` it doesn't have (SYNC-16).
import { api } from "@/api/client";
import { saveBlocked, saveDevice } from "@/features/devices/this-device";

import type { ShopDatabase } from "../db";
import { DEVICE_REFUSED, readDeviceRefused } from "./meta";
import type { DeviceRefusal, SyncPlace } from "./place";

/**
 * Keeps a refusal as the device check would:
 * - blocked: the lock goes on at once (03 §5.9, step 4); the database stays as it is, so an unblock
 *   finds its records still there.
 * - not registered: the saved copy is forgotten, and the top bar stops naming a shop this browser can't
 *   act for.
 */
export function keepOnThisPage(refusal: DeviceRefusal): void {
  if (refusal === "device.blocked") saveBlocked();
  else saveDevice(null);
}

/** The page's place: what sync.ts hands the push. */
export const pagePlace: SyncPlace = { api, hear: keepOnThisPage };

/**
 * Takes the note the service worker left (meta.ts, DEVICE_REFUSED) and keeps its refusal on this page, as
 * if the page had heard it itself: a phone blocked while the app was closed locks as it opens, with or
 * without a network (03 §5.9, step 4). True when there was one.
 *
 * Read and removed in one transaction, so two tabs opening at once don't both take it, and taken once
 * only: kept, it would block the laptop again after the manager's unblock. A note the page never took,
 * as it was blocked already (the moments stop, and a sync asks nothing), is thrown away by the device
 * check's next working answer (forgetBackgroundRefusal), so the unblock that follows doesn't find it.
 */
export async function heardInTheBackground(db: ShopDatabase): Promise<boolean> {
  const refusal = await db.transaction("rw", db.meta, async () => {
    const note = await readDeviceRefused(db);
    if (note !== null) await db.meta.delete(DEVICE_REFUSED);
    return note;
  });
  if (refusal === null) return false;
  keepOnThisPage(refusal);
  return true;
}

/**
 * Throws away the service worker's note, if any: the server has just said this device works, so a block
 * or a "not registered" the worker heard before is over. The device check calls it before it keeps that
 * answer (device-check.tsx). Without it, a note left while the page was blocked already would lock the
 * app again the moment the manager's unblock reached it (SYNC-16's review).
 *
 * A database that refused the delete is only logged: the answer must still be kept, and the note then
 * costs one more lock, put right by the next check.
 */
export async function forgetBackgroundRefusal(db: ShopDatabase): Promise<void> {
  try {
    await db.meta.delete(DEVICE_REFUSED);
  } catch (error) {
    console.error("the background's note was not forgotten", error);
  }
}
