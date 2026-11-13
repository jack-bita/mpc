// place.ts — what a push needs from where it runs: the page, or the service worker (SYNC-16, 03 §6.5).
//
// The page has cookies and localStorage; the service worker, which sends the outbox when the network
// comes back with the app closed, has neither. So the push imports neither: it is handed a place, with
// the client to call (whose CSRF token comes from that place's own cookies) and what to do when the
// server says the device itself is refused. The page's place is page-place.ts; the worker's is sw.ts's.

import type { ApiClient } from "@/api/client";

/** The two answers about the device itself (answer.ts): blocked by the manager, or a key that opens no
 * device. */
export type DeviceRefusal = "device.blocked" | "not_authenticated";

/** Keeps a refusal of the device where its place can: the page in localStorage, the worker in a note the
 * page reads (SYNC-16). Waited for before the refusal is thrown on, so it is kept even if the sync ends
 * there. */
export type HearDevice = (refusal: DeviceRefusal) => void | Promise<void>;

/** Where a push runs. */
export interface SyncPlace {
  api: ApiClient;
  hear: HearDevice;
}
