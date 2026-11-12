// sync.ts — one sync of this laptop's shop: the bootstrap if the database was never filled, then the
// push of what waits in the outbox (SYNC-8), then pulls until nothing more waits (SYNC-7, 03 §6.4); and
// the line each shop's syncs wait in, and the lock that keeps two tabs from syncing at once, so they run
// one after another (SYNC-9, 03 §6.5).
//
// It runs at the moments triggers.tsx keeps: as the app opens, when the network comes back, 2 s after a
// save, every 30 s while online, and from Tuma sasa (03 §6.5).
import { shopDatabase } from "../this-shop";
import { isAboutTheDevice } from "./answer";
import { bootstrap, needsBootstrap } from "./bootstrap";
import { mayPush, pushFailed, pushSettled } from "./backoff";
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
 * tests' jsdom, sync as before: one at a time in each tab.
 *
 * Honest limit: a call that never ends holds the lock, and every other tab waits behind it. The server
 * ends any call after 30 seconds (gunicorn's own limit), and the browser ends one whose network drops.
 */
async function inTurn(
  shopId: string,
  work: () => Promise<void>,
): Promise<void> {
  if (!("locks" in navigator)) return work();
  await navigator.locks.request(syncLockName(shopId), work);
}

async function syncOnce(shopId: string, sendNow: boolean): Promise<void> {
  const db = shopDatabase(shopId);
  // The first pull asks from the bootstrap's cursor, so the copy and the changes after it meet.
  if (await needsBootstrap(db)) await bootstrap(db);
  // The push before the pull: what this laptop made goes up first, so the pull that follows brings the
  // server's changes from it, and drops its pending effects as the cursor passes them. A push told to
  // try later still lets the pull run: the server's trouble saving one record doesn't stop the office's
  // changes coming down. After a failure, the next push waits a while (backoff.ts), in every tab, as the
  // wait is kept in the database; unless someone pressed Tuma sasa. The pull never waits.
  let pushFailure: { error: unknown } | null = null;
  if (sendNow || (await mayPush(db))) {
    let result: PushResult | null = null;
    try {
      result = await push(db);
    } catch (error) {
      await pushFailed(db);
      // Blocked, or a key that opens no device: ask nothing more (answer.ts has kept it).
      if (isAboutTheDevice(error)) throw error;
      // Any other failure, a 5xx on the push route say, still lets the pull run: the office's
      // changes, a suspension among them (X2), must not wait for the push to work again.
      pushFailure = { error };
    }
    if (result === "retry") await pushFailed(db);
    else if (result === "sent") await pushSettled(db);
  }
  await pull(db);
  // Thrown after the pull, so the failure is still reported (triggers.tsx). A pull that fails
  // too, as with no network, throws its own instead, which says the same.
  if (pushFailure !== null) throw pushFailure.error;
}
