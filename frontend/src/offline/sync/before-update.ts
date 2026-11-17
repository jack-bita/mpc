// before-update.ts — sends what waits in the outbox before the app switches to a new version (SYNC-13,
// 03 §6.8: send the outbox, then update the app, then upgrade the local database).
//
// The records go up in the shape the old app wrote them in, read by the old app's own code, before the new
// version takes over. The new version opens the database after the switch, and upgrades it then (db.ts):
// the last step of the order, with nothing to build here.
//
// Best effort, never a wall. The switch goes ahead, after trying, when the laptop has no network, when the
// send fails, or after SEND_LIMIT with no answer, as nothing is lost (Jack's plan, 13 Nov 2026):
// - the records stay in the outbox, in the database the new version opens, and it sends them;
// - the server reads the shape before its newest too (apps/sync/document_types.py), so a record written
//   by the old app is still taken from the new one;
// - a push cut off by the reload, with its answer lost, is sent again: the server answers `duplicate`
//   for a record it already holds, and keeps it once (03 §6.3);
// - the browser itself switches, with no bar, once every window of the app is closed (SPIKE-1), so the
//   new version must take over records the old one held, whatever this file does.
import { savedDevice } from "@/features/devices/this-device";

import { syncShop } from "./sync";
import { reportSyncFailure } from "./triggers";

/** How long a tap of Sasisha waits for the send before switching anyway. A push takes a second on the
 * shop's line; a server down would hold the person at the bar for the call's own limit, 2 minutes. */
export const SEND_LIMIT = 10_000;

/** One sync of a shop, as sync.ts runs it. Tests hand in their own. */
type Sync = typeof syncShop;

/**
 * Sends this laptop's waiting records, and settles once they are sent, the send failed, or SEND_LIMIT has
 * passed; never with a failure, as none of them stops the update.
 *
 * A sync with sendNow, as Tuma sasa asks: the push goes even while it waits after a failure (backoff.ts),
 * as someone tapped and waits to see it go. A whole sync, not the push alone: it takes the same lock and
 * line as every other sync of the shop (sync.ts), so it never sends the same records beside another tab's.
 */
export async function sendBeforeUpdate(sync: Sync = syncShop): Promise<void> {
  // A laptop not registered, or registered nowhere now, has no shop and nothing it may send.
  const shopId = savedDevice()?.shop.id;
  if (shopId === undefined) return;
  // No network at all (network.ts): the send could only fail. The new version sends them once it is back.
  if (!navigator.onLine) return;

  let timer: ReturnType<typeof setTimeout> | undefined;
  const limit = new Promise<void>((resolve) => {
    timer = setTimeout(resolve, SEND_LIMIT);
  });
  // A failure is reported as every sync's is (triggers.tsx), and the update goes on.
  const sent = sync(shopId, { sendNow: true }).catch(reportSyncFailure);
  await Promise.race([sent, limit]);
  clearTimeout(timer);
}
