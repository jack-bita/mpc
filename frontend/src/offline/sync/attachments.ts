// attachments.ts — sends the photos waiting on this laptop, each once its record is in (CTRL-6, 03 §5.13).
//
// A photo is saved with its record (outbox.ts) and waits in attachment_files, its bytes beside it in attachment_bytes. Its record goes first, with the push,
// and the server writes the photo's row from the record's label, in the record's own transaction (expect_attachment,
// ATT-3). Only then can the file be kept, so a photo goes only once its record is accepted: in sent_archive. A record
// still in the outbox, or set aside there (needs_attention), has no row on the server, and its photo waits with it.
//
// Each photo goes alone, to CTRL-3's route, `PUT /api/sync/v1/attachments/{id}/`, its body the file's bytes:
//
//   204 kept, the same file again, or a photo already removed → the laptop's copy goes (only a 204: any other
//                                answer that says all went well proves nothing, and stops the round)
//   404 attachment.not_found   → the server holds no row for it yet: it waits, and the others go on; after some
//                                two days of tries, it is set aside with that code (MOST_TRIES_NOT_FOUND)
//   400 too_big, not_an_image, file_differs → about the file itself, so the same file would get the same answer:
//                                set aside with its code, as the outbox sets a record aside, and the others go on
//   no answer, 411, one cut short on the way (400 cut_short), a server error, any other refusal → the round stops, and
//                                every photo waits for the next sync
//
// Each failed send makes that photo wait before its next one: 1 minute, then twice as long each time, at most an hour.
// The sync runs every 30 s, and a photo is some 150 KB: one the server keeps refusing would otherwise go 2,880 times
// a day, a whole bundle for nothing.
//
// Wi-Fi first, where the browser can tell (onCostlyLine): on mobile data, or when the person asked to save data,
// the photos wait. Where it can't tell, as Chrome on a Windows laptop can't, they go (Jack, 17 Nov 2026): about
// twenty clock-in photos a day come to some 3 MB, too little to need a setting.
//
// It runs in the page's sync alone, at its end (sync.ts): never in the service worker's push (SYNC-16), as a few
// minutes' wait for a photo costs nothing (the card's default).
//
// On the demo no visitor's clock-in photo leaves their laptop (Jack, ATT-3: A): the screen keeps none there
// (attendance.tsx), the server keeps no row there (post_clock), and this is the third lock, for a photo a laptop saved
// before it knew it belonged to the demo, as one whose saved copy came from before ATT-3 and tapped before its first
// check. Such photos are dropped from the laptop, never sent: their records went up without them, as `demo` or with
// a label the server writes no row for (ATT-3's review).
import Dexie from "dexie";

import { ApiRefusal, NoConnection } from "@/api/refusal";

import { isTheDemo, savedDevice } from "@/features/devices/this-device";

import { LARGEST_PHOTO } from "../attachments";
import type { AttachmentFileRow, ShopDatabase } from "../db";
import { isAboutTheDevice, syncAnswer, syncCallLimit } from "./answer";
import type { SyncPlace } from "./place";

/** At most this many bytes of photos go in one sync, 1.5 MB, about ten clock-in photos on a shop's slow line: the
 * sync holds its lock while they go (lock.ts), and a record saved meanwhile must not wait behind a week of photos.
 * Counted by size, not by number, as a photo of a supplier's paper may be far bigger than a face (STK-4). The first
 * photo of a sync always goes, whatever its size, so one of 1 MB is never stuck. The rest go at the next sync, 30 s
 * later. */
export const MOST_BYTES = LARGEST_PHOTO * 1.5;

/** The refusals that set a photo aside: each is about the file, never the line or the moment (CTRL-3). */
const SET_ASIDE = new Set([
  "attachment.too_big",
  "attachment.not_an_image",
  "attachment.file_differs",
]);

/** The server holds no row for the photo yet. Asked by its code, not its status: a 404 of another code (`not_found`,
 * a route this server doesn't have) is no answer about this photo, and stops the round. */
const NOT_FOUND = "attachment.not_found";

/** The try that gives up on a photo the server still can't find: the 54th, after some two days of waits (1 minute,
 * doubled each time, then an hour at a time). A photo goes only once its record is in, and the server writes its row
 * in the record's own transaction, so a row still missing by then is a bug in a record's handler, or a restore the
 * replay never put right (OPS-11): set aside with its code, the photo stops costing the shop's bundles every hour,
 * for good. Two days give a replay after a restore the time to bring the record back. Counted over every failed
 * send, a server error's too: each waits the same, so the count says how long the photo has been trying. */
export const MOST_TRIES_NOT_FOUND = 54;

/** The first wait after a failed send. */
export const FIRST_WAIT_MS = 60_000;

/** The longest wait: however long the trouble, a photo goes again at least once an hour. */
export const LONGEST_WAIT_MS = 60 * 60_000;

/** Takes every clock-in photo off a demo laptop, waiting or set aside, its row and its bytes together, so none can
 * ever go up (ATT-3's review). A short list: a demo laptop keeps none but those saved before it knew. */
async function dropTheDemosClockPhotos(db: ShopDatabase): Promise<void> {
  const ids = await db.attachment_files
    .filter((row) => row.kind === "clock_photo")
    .primaryKeys();
  if (ids.length === 0) return;
  await db.transaction(
    "rw",
    [db.attachment_files, db.attachment_bytes],
    async () => {
      await db.attachment_files.bulkDelete(ids);
      await db.attachment_bytes.bulkDelete(ids);
    },
  );
}

/** What Chrome, Edge and Android's browsers say of the line the device is on (the Network Information API). Not in
 * TypeScript's own list of the browser's parts, as Firefox and Safari have none: so each field may be missing. */
interface NetworkInformation {
  /** "wifi", "cellular" (mobile data), "ethernet"…; missing where the browser can't tell, as on a Windows laptop. */
  type?: string;
  /** True when the person turned on their browser's or phone's data saver. */
  saveData?: boolean;
}

/**
 * Whether the browser says the device is on a line that costs: mobile data, or a data saver turned on. A laptop on
 * a phone's hotspot sees only the Wi-Fi to the phone, and a browser that says nothing is taken at its word: the
 * photos then go (Jack, 17 Nov 2026).
 */
export function onCostlyLine(): boolean {
  const { connection } = navigator as Navigator & {
    connection?: NetworkInformation;
  };
  return connection?.saveData === true || connection?.type === "cellular";
}

/** What came back for one photo: kept, a refusal's code, or no answer at all. */
type Heard = { kept: true } | { kept: false; code: string | null };

/**
 * Sends the waiting photos whose records are in, oldest record first, one at a time, up to MOST_BYTES, unless the
 * device is on a costly line. A block or a "not registered" is kept (answer.ts) and thrown on, as the sync must then
 * ask nothing more; any other failure only ends the round, as the next sync tries again.
 */
export async function sendAttachments(
  db: ShopDatabase,
  place: SyncPlace,
): Promise<void> {
  // The demo's third lock, before anything is read for sending.
  if (isTheDemo(savedDevice())) await dropTheDemosClockPhotos(db);
  // Only their ids first, then each one's small row as it comes: the bytes are read only for the photo that goes.
  const ids = await waitingInOrder(db).primaryKeys();
  let sentBytes = 0;
  for (const id of ids) {
    // Asked before each photo: a device that leaves the shop's Wi-Fi for mobile data mid-round stops sending at once.
    // Waiting for Wi-Fi is no failed send: the photo's wait and tries stay as they were.
    if (onCostlyLine()) return;
    const photo = await readyToGo(db, id);
    if (photo === null) continue;
    // Over this sync's share: it goes first at the next one, still in its order, never passed by a smaller one.
    if (sentBytes > 0 && sentBytes + photo.size > MOST_BYTES) return;
    sentBytes += photo.size;
    const kept = await db.attachment_bytes.get(id);
    // Written in one transaction with its row (outbox.ts), and deleted with it, so never missing.
    if (kept === undefined) throw new Error(`Photo ${id} has no bytes.`);
    const { bytes } = kept;
    // The wait counts from when it went, not from when its answer came, as the push's does (backoff.ts).
    const sentAt = Date.now();
    const heard = await send(photo, bytes, place);
    const tries = photo.tries + 1;
    if (heard.kept) {
      // Kept on the server: this laptop's copy is no longer needed, its row and its bytes together.
      await db.transaction(
        "rw",
        [db.attachment_files, db.attachment_bytes],
        async () => {
          await db.attachment_files.delete(photo.id);
          await db.attachment_bytes.delete(photo.id);
        },
      );
    } else if (
      heard.code !== null &&
      (SET_ASIDE.has(heard.code) ||
        (heard.code === NOT_FOUND && tries >= MOST_TRIES_NOT_FOUND))
    ) {
      await db.attachment_files.update(photo.id, {
        state: "set_aside",
        tries,
        last_error: heard.code,
        wait_until: null,
      });
    } else {
      await db.attachment_files.update(photo.id, {
        tries,
        last_error: heard.code,
        wait_until: sentAt + waitAfter(tries),
      });
      // A row not there yet is this photo's alone; anything else is the line's or the server's.
      if (heard.code !== NOT_FOUND) return;
    }
  }
}

/** The waiting photos, in their records' order: the outbox's own order, so photos go as their records did. */
function waitingInOrder(db: ShopDatabase) {
  return db.attachment_files
    .where("[state+device_seq]")
    .between(["waiting", Dexie.minKey], ["waiting", Dexie.maxKey]);
}

// The photo's row, if it is still waiting, its wait is over, and its record is in; otherwise null. Read in one
// transaction, so the photo and its record are seen as they stood together. Its bytes are read after, only for the
// photo that goes.
async function readyToGo(
  db: ShopDatabase,
  id: string,
): Promise<AttachmentFileRow | null> {
  return db.transaction(
    "r",
    [db.attachment_files, db.sent_archive],
    async () => {
      const photo = await db.attachment_files.get(id);
      if (photo === undefined || photo.state !== "waiting") return null;
      if (!waitIsOver(photo.wait_until)) return null;
      // Accepted: the push moved its record to sent_archive (push.ts), in the transaction that read its answer.
      const accepted = await db.sent_archive
        .where("id")
        .equals(photo.document_id)
        .count();
      return accepted > 0 ? photo : null;
    },
  );
}

// How long a photo waits after its nth failed send: 1 minute, doubled each time, at most an hour.
function waitAfter(tries: number): number {
  return Math.min(FIRST_WAIT_MS * 2 ** (tries - 1), LONGEST_WAIT_MS);
}

function waitIsOver(until: number | null): boolean {
  if (until === null) return true;
  const left = until - Date.now();
  // No real wait is longer than the longest: more left means the laptop's clock was put back (03 §6.6), and the
  // photo would wait for as long as it moved (as the push's wait, backoff.ts).
  return left <= 0 || left > LONGEST_WAIT_MS;
}

// One photo to the server, and what came back.
async function send(
  photo: AttachmentFileRow,
  bytes: ArrayBuffer,
  place: SyncPlace,
): Promise<Heard> {
  try {
    let status = 0;
    await syncAnswer(
      place.api
        .PUT("/api/sync/v1/attachments/{id}/", {
          params: { path: { id: photo.id } },
          // The file's bytes alone, no JSON and no form (CTRL-3). The server's description names the body a string, as
          // OpenAPI writes any file, so the bytes are handed over as they are, past the client's JSON. fetch gives an
          // ArrayBuffer its length, so the route never has to answer 411 for want of one.
          body: bytes as unknown as string,
          bodySerializer: (body) => body,
          // Its type as the label says: the server checks it against the file's first bytes.
          headers: { "Content-Type": photo.content_type },
          signal: syncCallLimit(),
        })
        .then((answer) => {
          status = answer.response.status;
          return answer;
        }),
      place.hear,
    );
    // Only the route's own "kept", 204 (CTRL-3), takes the photo off the laptop, which can't be undone: any other
    // answer that says all went well is one the route never gives, so nothing proves the file is kept. The photo
    // stays, waits, and the round stops, as after an answer the laptop can't read.
    return status === 204 ? { kept: true } : { kept: false, code: null };
  } catch (error) {
    if (error instanceof NoConnection) return { kept: false, code: null };
    // Blocked, or a key that opens no device: kept by syncAnswer, and thrown on, so the sync asks nothing more.
    if (error instanceof ApiRefusal && !isAboutTheDevice(error))
      return { kept: false, code: error.body.code };
    throw error;
  }
}
