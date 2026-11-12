// backoff.ts — how long a shop's next push waits after the server said "try later", or a push failed
// (SYNC-8, 03 §6.5).
//
// A server in trouble, or a line that keeps dropping, must not get the same push from every laptop every
// few seconds. So after each failure the next push waits: 30 s, then twice as long each time, never more
// than 5 minutes. A push that settles starts it again from 30 s. Only the push waits: the pull still runs,
// so the office's changes keep coming down; and Tuma sasa doesn't wait (sync.ts).
//
// Kept in the shop's own database, as two of the sync's notes in `meta` (SYNC-9): every tab of the app
// sees the same wait, so a second tab can't push the moment the first was told to wait, and a reload
// waits too. Per shop, as each shop has its database: a laptop may hold the practice shop beside the live
// one, and one shop's trouble is not the other's. A reset of the database forgets it, with everything
// else, and costs one push at most.
import type { ShopDatabase } from "../db";
import { PUSH_WAIT_NEXT, PUSH_WAIT_UNTIL } from "./meta";

/** The first wait, after one failure. */
const FIRST_WAIT_MS = 30_000;

/** The longest wait: however long the trouble, the laptop tries again every 5 minutes. */
const LONGEST_WAIT_MS = 5 * 60_000;

/** How early a moment may land and still count as the wait's end. The 30 s ticks (triggers.tsx) and the
 * wait start a few milliseconds apart: the tick fires, then the sync reads its notes, then the push goes.
 * So the tick 30 s later lands a hair before the wait ends, and without this it would skip the push,
 * making every wait one tick longer than 03 §6.5 says. Far shorter than a second, so a wait never ends
 * a whole second early. */
const ON_TIME_MS = 500;

// A note's number, or none: a note an older app wrote some other way reads as none.
async function readNumber(
  db: ShopDatabase,
  key: string,
): Promise<number | null> {
  const row = await db.meta.get(key);
  return typeof row?.value === "number" ? row.value : null;
}

/** Whether the shop's push may go now: no wait, or its wait is over. */
export async function mayPush(db: ShopDatabase): Promise<boolean> {
  const until = await readNumber(db, PUSH_WAIT_UNTIL);
  if (until === null) return true;
  const left = until - Date.now();
  // No real wait is longer than the longest: more left means the laptop's clock was put back (a shop
  // laptop's clock is often wrong, 03 §6.6), and the wait would run on for as long as it moved.
  return left <= ON_TIME_MS || left > LONGEST_WAIT_MS;
}

/**
 * The server said "try later", or the push failed: the next one waits, longer than the last time. The
 * wait counts from `pushedAt`, when the push went, not from when its answer came: on a slow line the
 * answer may take seconds, and a wait counted from it would end after the next tick, so the push would
 * wait a whole tick more. Read and written in one transaction, so two failures at once never both start
 * from the same length.
 */
export async function pushFailed(
  db: ShopDatabase,
  pushedAt: number,
): Promise<void> {
  await db.transaction("rw", db.meta, async () => {
    const length = (await readNumber(db, PUSH_WAIT_NEXT)) ?? FIRST_WAIT_MS;
    await db.meta.bulkPut([
      { key: PUSH_WAIT_UNTIL, value: pushedAt + length },
      { key: PUSH_WAIT_NEXT, value: Math.min(length * 2, LONGEST_WAIT_MS) },
    ]);
  });
}

/** Every record sent got an answer that settles it: the next trouble waits from 30 s again. */
export async function pushSettled(db: ShopDatabase): Promise<void> {
  await db.meta.bulkDelete([PUSH_WAIT_UNTIL, PUSH_WAIT_NEXT]);
}
