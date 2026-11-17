// meta.ts — the sync's own notes in a shop's database: their names in the meta drawer, and how each is
// read (SYNC-7, 03 §6.1). Kept in one file so the bootstrap, the pull and the screens that read the
// clock (SYNC-11) agree on every name.
import type { ShopDatabase } from "../db";
import type { DeviceRefusal } from "./place";

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

/** What the server said about the device to the service worker, when it answered a background push with
 * a block or a "not registered" (SYNC-16): "device.blocked" or "not_authenticated". The worker has no
 * localStorage, where the page keeps the device's standing (this-device.ts), so it leaves this note, and
 * the page takes it as it opens and before each sync (page-place.ts). Missing while there is nothing to
 * tell. Kept in the shop's database, as the worker knows the shop and nothing else. */
export const DEVICE_REFUSED = "device_refused";

/** The cursor, or null when this database was never filled. */
export async function readCursor(db: ShopDatabase): Promise<number | null> {
  const row = await db.meta.get(CURSOR);
  return typeof row?.value === "number" ? row.value : null;
}

/** The server's time at the last pull, as it sent it, or null before the laptop's first pull: a bootstrap
 * alone doesn't bring it. A clock-in needs it, as the server refuses one without (ATT-1, SYNC-11). */
export async function readLastServerTime(
  db: ShopDatabase,
): Promise<string | null> {
  const row = await db.meta.get(LAST_SERVER_TIME);
  return typeof row?.value === "string" ? row.value : null;
}

/** The laptop's last record number, or null when this database was never filled. */
export async function readLastDeviceSeq(
  db: ShopDatabase,
): Promise<number | null> {
  const row = await db.meta.get(LAST_DEVICE_SEQ);
  return typeof row?.value === "number" ? row.value : null;
}

/** The refusal the service worker heard, or null: a note some other app wrote reads as none. */
export async function readDeviceRefused(
  db: ShopDatabase,
): Promise<DeviceRefusal | null> {
  const row = await db.meta.get(DEVICE_REFUSED);
  return row?.value === "device.blocked" || row?.value === "not_authenticated"
    ? row.value
    : null;
}

/** Leaves the note for the page: the service worker's way of keeping a refusal (SYNC-16). */
export async function noteDeviceRefused(
  db: ShopDatabase,
  refusal: DeviceRefusal,
): Promise<void> {
  await db.meta.put({ key: DEVICE_REFUSED, value: refusal });
}
