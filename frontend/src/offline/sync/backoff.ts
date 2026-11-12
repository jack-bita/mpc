// backoff.ts — how long a shop's next push waits after the server said "try later", or a push failed
// (SYNC-8, 03 §6.5).
//
// A server in trouble, or a line that keeps dropping, must not get the same push from every laptop every
// few seconds. So after each failure the next push waits: 30 s, then twice as long each time, never more
// than 5 minutes. A push that settles starts it again from 30 s. Only the push waits: the pull still runs,
// so the office's changes keep coming down.
//
// Kept in memory, per shop: a laptop may hold the practice shop beside the live one, and one shop's
// trouble is not the other's. A reload forgets the wait, which costs one push at most.

/** The first wait, after one failure. */
const FIRST_WAIT_MS = 30_000;

/** The longest wait: however long the trouble, the laptop tries again every 5 minutes. */
const LONGEST_WAIT_MS = 5 * 60_000;

/** A shop's wait: when its push may go again, and how long the wait after the next failure will be. */
interface Wait {
  until: number;
  next: number;
}

const waits = new Map<string, Wait>();

/** Whether the shop's push may go now: no wait, or its wait is over. */
export function mayPush(shopId: string): boolean {
  const wait = waits.get(shopId);
  if (wait === undefined) return true;
  const left = wait.until - Date.now();
  // No real wait is longer than the longest: more left means the laptop's clock was put back (a shop
  // laptop's clock is often wrong, 03 §6.6), and the wait would run on for as long as it moved.
  return left <= 0 || left > LONGEST_WAIT_MS;
}

/** The server said "try later", or the push failed: the next one waits, longer than the last time. */
export function pushFailed(shopId: string): void {
  const length = waits.get(shopId)?.next ?? FIRST_WAIT_MS;
  waits.set(shopId, {
    until: Date.now() + length,
    next: Math.min(length * 2, LONGEST_WAIT_MS),
  });
}

/** Every record sent got an answer that settles it: the next trouble waits from 30 s again. */
export function pushSettled(shopId: string): void {
  waits.delete(shopId);
}

/** Forgets every wait. Tests only, so each starts on a laptop that never failed a push. */
export function forgetPushWaits(): void {
  waits.clear();
}
