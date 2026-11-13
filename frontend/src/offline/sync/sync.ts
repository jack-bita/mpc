// sync.ts — one sync of this laptop's shop: the bootstrap if the database was never filled, then the
// push of what waits in the outbox (SYNC-8), then pulls until nothing more waits (SYNC-7, 03 §6.4); and
// the line each shop's syncs wait in, and the lock that keeps two tabs from syncing at once, so they run
// one after another (SYNC-9, 03 §6.5).
//
// It runs at the moments triggers.tsx keeps: as the app opens, when the network comes back, 2 s after a
// save, every 30 s while online, and from Tuma sasa (03 §6.5).
import { hasCsrfToken } from "@/api/client";
import { savedBlocked } from "@/features/devices/this-device";

import type { ShopDatabase } from "../db";
import { shopDatabase } from "../this-shop";
import { isAboutTheDevice } from "./answer";
import { bootstrap, needsBootstrap } from "./bootstrap";
import { mayPush, pushFailed, pushSettled } from "./backoff";
import { heardInTheBackground, pagePlace } from "./page-place";
import { pull } from "./pull";
import { push, type PushResult } from "./push";

/** What a sync is asked for. */
export interface SyncAsk {
  /** *Tuma sasa*: the push goes even while it waits after a failure. Someone pressed the button and is
   * there to see it go (Jack, 12 Nov 2026); one press is one push, never a flood. A failure still makes
   * the next wait longer. */
  sendNow?: boolean;
}

// A shop's syncs in this tab: the one running, and at most one asked for while it runs. Kept by shop: a
// laptop moved to another shop mid-sync starts that shop's own, never waiting behind the old shop's.
// This tab only: two tabs are kept apart by the lock (inTurn, below).
interface Line {
  running: Promise<void>;
  next: Next | null;
}

// The sync asked for while one runs. Its sendNow can still change: a press of Tuma sasa while it waits
// to start makes it push.
interface Next {
  sendNow: boolean;
  done: Promise<void>;
}

const lines = new Map<string, Line>();

/**
 * Syncs the shop's database: fills it once, then pushes, then pulls. A failure is thrown, after a block
 * or a "not registered" was kept (answer.ts); whatever was saved before it stays, and the next sync goes
 * on from there.
 *
 * Asked while one runs, it runs once more right after it: the running one may have pushed already, and a
 * record saved since must not wait for the next moment (03 §6.5). Asked again before that one starts, it
 * joins it: however many asks come in, one runs and one waits, never more. The one after runs however
 * the one before ended: a failed sync is the next one's to put right.
 */
export function syncShop(shopId: string, ask: SyncAsk = {}): Promise<void> {
  const sendNow = ask.sendNow === true;
  const line = lines.get(shopId);
  if (line === undefined) {
    const fresh: Line = { running: Promise.resolve(), next: null };
    lines.set(shopId, fresh);
    fresh.running = runInLine(shopId, fresh, sendNow);
    return fresh.running;
  }
  if (line.next !== null) {
    // One already waits to start: this ask is the same one, and a Tuma sasa makes it push.
    line.next.sendNow ||= sendNow;
    return line.next.done;
  }
  const next: Next = { sendNow, done: Promise.resolve() };
  next.done = line.running
    // However the one before ended: its failure was thrown to whoever asked for it.
    .then(nothing, nothing)
    .then(() => {
      // It starts now, so it is the one running, and an ask from here on waits behind it.
      line.next = null;
      line.running = next.done;
      return runInLine(shopId, line, next.sendNow);
    });
  line.next = next;
  return next.done;
}

function nothing(): void {}

// One sync, then the line is ended, unless another waits to start. Only this line's own entry is
// removed: a line is never replaced while it runs, but the check costs nothing.
async function runInLine(
  shopId: string,
  line: Line,
  sendNow: boolean,
): Promise<void> {
  try {
    await inTurn(shopId, () => syncOnce(shopId, sendNow));
  } finally {
    if (line.next === null && lines.get(shopId) === line) lines.delete(shopId);
  }
}

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
 * A call left hanging would hold the lock, and every other tab would wait behind it: each sync call gives
 * up after 2 minutes (syncCallLimit, answer.ts), as if the network had dropped, and the lock goes on.
 */
async function inTurn(
  shopId: string,
  work: () => Promise<void>,
): Promise<void> {
  if (!("locks" in navigator)) return work();
  await navigator.locks.request(syncLockName(shopId), work);
}

async function syncOnce(shopId: string, sendNow: boolean): Promise<void> {
  // A sync that waited its turn, behind this tab's last one or another tab's, may start after the
  // laptop heard of its block (a refusal kept by answer.ts, in any tab). It then asks nothing: the server
  // would refuse it, and a blocked laptop must stop asking (03 §5.9, step 4). The moments stop too
  // (triggers.tsx); this catches the one already in line.
  if (savedBlocked()) return;
  const db = shopDatabase(shopId);
  // The same for a block the service worker heard while this page was open (SYNC-16): it is kept now,
  // and nothing is asked.
  if (await heardInTheBackground(db)) return;
  // The first pull asks from the bootstrap's cursor, so the copy and the changes after it meet.
  if (await needsBootstrap(db)) await bootstrap(db);
  // The push before the pull: what this laptop made goes up first, so the pull that follows brings the
  // server's changes from it, and drops its pending effects as the cursor passes them. A push told to
  // try later still lets the pull run: the server's trouble saving one record doesn't stop the office's
  // changes coming down. After a failure, the next push waits a while (backoff.ts), in every tab, as the
  // wait is kept in the database; unless someone pressed Tuma sasa. The pull never waits.
  //
  // No push before the server has given this browser its CSRF token: the push is a change, and would be
  // refused (403), then wait 30 s for nothing. The token comes with the device check's answer
  // (DeviceMeView), a moment after the app opens, and the next moment pushes. A laptop has it already,
  // from its last visit, unless the browser lost it; the pull, a read, needs none.
  let pushFailure: { error: unknown } | null = null;
  if (hasCsrfToken() && (sendNow || (await mayPush(db)))) {
    let result: PushResult | null = null;
    // The wait after a failure counts from here, when the push went (backoff.ts says why).
    const pushedAt = Date.now();
    try {
      result = await push(db, pagePlace);
    } catch (error) {
      await waitAfterAFailure(db, pushedAt);
      // Blocked, or a key that opens no device: ask nothing more (answer.ts has kept it).
      if (isAboutTheDevice(error)) throw error;
      // Any other failure, a 5xx on the push route say, still lets the pull run: the office's
      // changes, a suspension among them (X2), must not wait for the push to work again.
      pushFailure = { error };
    }
    if (result === "retry") await waitAfterAFailure(db, pushedAt);
    else if (result === "sent") await pushSettled(db);
  }
  await pull(db);
  // Thrown after the pull, so the failure is still reported (triggers.tsx). A pull that fails
  // too, as with no network, throws its own instead, which says the same.
  if (pushFailure !== null) throw pushFailure.error;
}

// The wait after a failure, written without hiding the failure itself. A wait the database refused to keep
// (a full disk, say) costs one early push at most. Thrown, it would take the place of the push's own
// failure, the one worth reporting, and stop the pull, which must still run (X2): so it is only logged.
async function waitAfterAFailure(
  db: ShopDatabase,
  pushedAt: number,
): Promise<void> {
  try {
    await pushFailed(db, pushedAt);
  } catch (error) {
    console.error("the push's wait was not kept", error);
  }
}
