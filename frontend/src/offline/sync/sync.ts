// sync.ts — one sync of this laptop's shop: the bootstrap if the database was never filled, then the
// push of what waits in the outbox (SYNC-8), then pulls until nothing more waits (SYNC-7, 03 §6.4).
//
// For now it runs after each device check that names a working device (device-check.tsx): as the app
// opens, when its window comes back to the front, when the network returns, and every 5 minutes. That is
// enough for an office change to reach the counter. SYNC-9 brings the full set of moments (03 §6.5) and
// a lock so two tabs never sync at once (Web Locks).
import { shopDatabase } from "../this-shop";
import { bootstrap, needsBootstrap } from "./bootstrap";
import { pull } from "./pull";
import { push } from "./push";

// The sync running now in this tab, for each shop. A check that lands while one still runs joins it
// instead of starting a second, which would ask for the same pages and write them twice. Kept by shop: a
// laptop moved to another shop mid-sync starts that shop's own, never joining the old shop's. Other tabs
// are SYNC-9's.
const running = new Map<string, Promise<void>>();

/**
 * Syncs the shop's database: fills it once, then pushes, then pulls. A failure is thrown, after a block
 * or a "not registered" was kept (answer.ts); whatever was saved before it stays, and the next sync goes
 * on from there.
 */
export function syncShop(shopId: string): Promise<void> {
  const already = running.get(shopId);
  if (already !== undefined) return already;
  const sync = (async () => {
    const db = shopDatabase(shopId);
    // The first pull asks from the bootstrap's cursor, so the copy and the changes after it meet.
    if (await needsBootstrap(db)) await bootstrap(db);
    // The push before the pull: what this laptop made goes up first, so the pull that follows brings the
    // server's changes from it, and drops its pending effects as the cursor passes them. A push told to
    // try later still lets the pull run: the server's trouble saving one record doesn't stop the office's
    // changes coming down.
    await push(db);
    await pull(db);
  })().finally(() => {
    running.delete(shopId);
  });
  running.set(shopId, sync);
  return sync;
}
