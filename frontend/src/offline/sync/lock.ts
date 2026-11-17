// lock.ts — the lock that keeps two syncs of a shop apart, whoever runs them: two tabs of the app, or a
// tab and the service worker, which pushes when the network comes back with the app closed (SYNC-9,
// SYNC-16, 03 §6.5). Its own file, with nothing of the page's, so the worker takes the very same lock.

/** The lock's name: one per shop, as its database is (db.ts), so the practice shop's sync never waits for
 * the live shop's. */
export function syncLockName(shopId: string): string {
  return `mpc-sync-${shopId}`;
}

/**
 * Runs a sync once no other tab of the app is syncing the same shop (03 §6.5). Two tabs syncing at once
 * would send the same records together and apply the same pages twice; one at a time, each starts where
 * the last one ended.
 *
 * The browser's Web Locks: a lock by name, shared by every tab of the app's address, given to one at a
 * time, in the order asked, and handed on as soon as the work ends, however it ended, or as its tab
 * closes. A tab that asks while another holds it waits, never skips: a record it just saved must still
 * go, and the other tab's push may have read its outbox before the save.
 *
 * Chrome and Edge, the shop's browsers (03 §7.3), have had it for years. A browser without it, and the
 * tests' jsdom, sync as before: one at a time in each tab. So does a page opened on a plain http address
 * other than localhost (a phone trying a developer's laptop over Wi-Fi): browsers give Web Locks only to
 * https and localhost, and two tabs there are not kept apart. The shop's server and the demo are https.
 *
 * The service worker asks for the same lock by the same name (background.ts): a push of its own while a
 * tab pushes would send the same records twice at once.
 *
 * A call left hanging would hold the lock, and every other tab would wait behind it: each sync call gives
 * up after 2 minutes (syncCallLimit, answer.ts), as if the network had dropped, and the lock goes on.
 */
export async function inTurn(
  shopId: string,
  work: () => Promise<void>,
): Promise<void> {
  if (!("locks" in navigator)) return work();
  await navigator.locks.request(syncLockName(shopId), work);
}
