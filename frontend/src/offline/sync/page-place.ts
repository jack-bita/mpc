// page-place.ts — the page's place for a sync (place.ts): the app's own client, and a refusal of the
// device kept in localStorage, as the device check keeps it (this-device.ts, 03 §5.9).
//
// Kept apart from push.ts and answer.ts so the service worker, which bundles those, never pulls in the
// page's device copy, React's hooks and all, nor reaches for a `window` it doesn't have (SYNC-16).
import { api } from "@/api/client";
import { saveBlocked, saveDevice } from "@/features/devices/this-device";

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
