// meta.ts — the sync's own notes in a shop's database: their names in the meta drawer, and how each is
// read (SYNC-7, 03 §6.1). Kept in one file so the bootstrap, the pull and the screens that read the
// clock (SYNC-11) agree on every name.
import type { ShopDatabase } from "../db";

/** The shop's last change number this database holds: the next pull asks for what came after it.
 * Missing until the first bootstrap, which is how the app knows a laptop still needs one. */
export const CURSOR = "pull_cursor";

/** How far the server's clock is ahead of this laptop's, in milliseconds (03 §6.6): a shop laptop's
 * clock is often wrong, and a time worked out on it must be put right by this much. */
export const CLOCK_OFFSET = "clock_offset_ms";

/** The server's own time at the last pull, as it sent it (UTC). A clock-in writes it into its document
 * when the tap is saved, so the server can tell how long ago the laptop last heard from it (ATT-1). */
export const LAST_SERVER_TIME = "last_server_time";

/** The number of the last record this laptop saved (03 §6.3): the next one is this plus one, and no
 * two records share a number (SYNC-4). The first bootstrap sets it from the server's count (SYNC-8),
 * and each save moves it in the save's own transaction (outbox.ts). Here, though a reset of this
 * database wipes it: the server's count survives a wipe, and the bootstrap that fills the laptop again
 * brings it back, where the browser's other storage would be wiped with the database. Missing until a
 * bootstrap brings it, so a laptop never filled saves nothing; one filled before SYNC-8 has a cursor but
 * no number, and is filled again (needsBootstrap). */
export const LAST_DEVICE_SEQ = "last_device_seq";

/** When the next push may go, in milliseconds by the laptop's clock, after the server said "try later"
 * or a push failed (backoff.ts). Kept here, not in a tab's memory, so every tab waits alike (SYNC-9).
 * Missing while no push waits. */
export const PUSH_WAIT_UNTIL = "push_wait_until_ms";

/** How long the wait after the next failure will be, in milliseconds: twice the last, at most 5 minutes
 * (backoff.ts). Missing while no push waits, so the next trouble waits 30 s. */
export const PUSH_WAIT_NEXT = "push_wait_next_ms";

/** The cursor, or null when this database was never filled. */
export async function readCursor(db: ShopDatabase): Promise<number | null> {
  const row = await db.meta.get(CURSOR);
  return typeof row?.value === "number" ? row.value : null;
}

/** The laptop's last record number, or null when this database was never filled. */
export async function readLastDeviceSeq(
  db: ShopDatabase,
): Promise<number | null> {
  const row = await db.meta.get(LAST_DEVICE_SEQ);
  return typeof row?.value === "number" ? row.value : null;
}
