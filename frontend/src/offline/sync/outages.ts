// outages.ts — this laptop's offline periods (SYNC-14, 03 §6.11): when it lost the server, and when it
// heard it again. It owns the `outages` drawer's rules: one open period at a time, kept up while an open
// app still sees the laptop cut off, and closed when the server answers. The push sends the closed ones
// (push.ts), and the office's *Hali ya vifaa* shows them; at R2 they decide whether a local hub is worth
// building (ADR-0030).
//
// Who tells it what:
// - the moments (triggers.tsx): the browser's `offline` event, and each moment met with no network at all,
//   say "cut off"; each moment with a network says "still here", which keeps an open period up while a
//   sync waits for an answer that may never come;
// - the sync (sync.ts): a pull that got an answer says "back"; a call that got none (NoConnection) says
//   "cut off". So a Wi-Fi with no internet behind it counts, though the browser says it is online.
//
// Every time is the laptop's own clock, as the server keeps it (02: DeviceOutage), so a period may even
// end before it starts after the clock was put back: the office page shows it as the laptop said.
//
// No `window` here, and every time is handed in: the service worker loads this file through push.ts
// (tsconfig.sw.json checks it), and the tests choose the clock.
import type { components } from "@/api/schema";
import { newId } from "@/lib/ids";

import type { OutageRow, ShopDatabase } from "../db";

/**
 * How long an open period may go unseen before the app is taken to have been away, closed or asleep:
 * 3 minutes. An open app sees it at every moment, every 30 s (SYNC_EVERY); Chrome slows the moments of a
 * tab left hidden to about once a minute, so 3 minutes leaves room for that, and for a reload.
 *
 * A period the app lost sight of ends where it last saw it, not when the app opens again: a laptop shut
 * at 19:00 with no internet, and opened at 07:30 with it, was seen cut off until 19:00, and nobody knows
 * about the night. Counting the night would make the shop's cuts look far longer than they are.
 */
export const LOST_SIGHT = 3 * 60_000;

/**
 * The laptop can't reach the server, at `now`: the network went, a moment met none, or a call got no
 * answer. Keeps the open period up, or opens one if none is.
 */
export async function noteCutOff(db: ShopDatabase, now: number): Promise<void> {
  // One transaction: two tabs that lose the network together take turns here, so the second finds the
  // first one's period and keeps it up, rather than opening a second one for the same cut.
  await db.transaction("rw", db.outages, async () => {
    const open = await settleOpen(db, now);
    if (open !== null) {
      await db.outages.update(open.id, { seen_at: at(now) });
      return;
    }
    await db.outages.add({
      id: newId(),
      started_at: at(now),
      ended_at: null,
      seen_at: at(now),
      end_unknown: false,
    });
  });
}

/**
 * An open app is still here at `now`, the network maybe back, maybe not: keeps an open period up, and
 * opens none. A sync whose calls hang on a lost line answers only after its time limit (answer.ts, 2
 * minutes a call); without this, the period would look unseen meanwhile, and be cut in two.
 */
export async function noteStillHere(
  db: ShopDatabase,
  now: number,
): Promise<void> {
  await db.transaction("rw", db.outages, async () => {
    const open = await settleOpen(db, now);
    if (open !== null) await db.outages.update(open.id, { seen_at: at(now) });
  });
}

/** The server answered at `now`: the open period, if any, ends then. */
export async function noteBack(db: ShopDatabase, now: number): Promise<void> {
  await db.transaction("rw", db.outages, async () => {
    const open = await settleOpen(db, now);
    if (open !== null)
      await db.outages.update(open.id, { ended_at: at(now), seen_at: at(now) });
  });
}

/**
 * Closes, at the last time it was seen, each open period the app lost sight of, and gives back the one
 * still in sight, if any. Inside the caller's transaction. One closed so says its end is unknown: the
 * laptop went off, its battery flat in a power cut, or the app was closed or asleep, and the cut may
 * have gone on long after. The page shows it as "18:59 – ?" (Jack, SYNC-14's review), never as a short
 * cut the shop didn't have.
 *
 * Only one should ever be open; a second, which a bug could leave, is closed too rather than kept open
 * for good. A clock put back makes `now` earlier than the last sight: that period counts as in sight, as
 * nothing says the app was away.
 */
async function settleOpen(
  db: ShopDatabase,
  now: number,
): Promise<OutageRow | null> {
  const open = await db.outages
    .filter((row) => row.ended_at === null)
    .toArray();
  let inSight: OutageRow | null = null;
  for (const row of open) {
    if (inSight === null && now - Date.parse(row.seen_at) <= LOST_SIGHT) {
      inSight = row;
      continue;
    }
    await db.outages.update(row.id, {
      ended_at: row.seen_at,
      end_unknown: true,
    });
  }
  return inSight;
}

/** At most this many periods a push, as the server takes (PushBatch's `outages`, 03 §6.3). */
export const MOST_OUTAGES = 100;

/** A period as the push sends it (03 §6.3): no `seen_at`, which is the laptop's own. */
export type SentOutage = components["schemas"]["OutageEnvelopeRequest"];

/**
 * The closed periods the next push sends, at most MOST_OUTAGES, in the drawer's id order. That is mostly
 * the order they were made in, an id being a UUIDv7 that starts with this laptop's clock, but not surely:
 * a clock put back makes a later id smaller (lib/ids.ts). No matter: the server keeps each by its id, in
 * any order, and the page sorts them itself. An open one waits until it closes: the server keeps a period
 * once, as first sent (DeviceOutage), so it must go whole. Read inside the push's own transaction, with its
 * batch (push.ts).
 */
export async function periodsToSend(db: ShopDatabase): Promise<SentOutage[]> {
  const closed = await db.outages
    .filter((row) => row.ended_at !== null)
    .limit(MOST_OUTAGES)
    .toArray();
  // The filter kept only the closed ones; asked again here so TypeScript knows `ended_at` is a time.
  return closed.flatMap(({ id, started_at, ended_at, end_unknown }) =>
    ended_at === null ? [] : [{ id, started_at, ended_at, end_unknown }],
  );
}

/** A time of this laptop's clock, as the push sends every time: in UTC, with its `Z` (ATT-1). */
function at(now: number): string {
  return new Date(now).toISOString();
}
