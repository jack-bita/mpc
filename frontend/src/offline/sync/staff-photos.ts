// staff-photos.ts — brings the workers' photos down, for their tiles on the PIN screen (PPL-14, 03 §5.13).
//
// A staff row names the photo its person shows, by the photo's id, never the picture (StaffRecord). So at the end of
// each page's sync, once the pull has brought the rows up to date, the laptop makes the photos it holds match them:
//
//   a photo here that no row names any more → dropped: replaced, taken off, its person left or was switched off
//   a photo a row names that isn't here     → asked for, `GET /api/sync/v1/staff-photos/{id}/`, and kept
//
// Kept as its bytes in staff_photos (db.ts), so the tiles show it with no network too. A changed photo is a new id, so
// one kept is never asked for again, and the server hands out only a photo a row of this laptop's list names
// (staff_photo, apps/sync/selectors.py).
//
// What may come, one photo at a time:
//
//   200, a JPEG or a WebP of 1 MB at most → kept, if a row still names it by then
//   404 attachment.…  about this photo    → changed since the pull, which will say to what: it waits, the others go on
//   200, anything else                    → nothing the server hands out, so something else answered, as a Wi-Fi's own
//                                           login page does: it waits, and the round stops
//   no answer, a server error, any other refusal → it waits, and the round stops
//   401 device.blocked or not_authenticated → kept by answer.ts and thrown on, as the sync must ask nothing more
//
// A photo that didn't come, or came and couldn't be kept, waits before it is asked for again, as one going up does: 1
// minute, then twice as long each time, at most an hour, or a photo whose file the server lost would be asked for 2,880
// times a day. The waits live in the page's memory: a reload asks once more, which costs one call; and until it comes,
// the tile shows the names.
//
// Wi-Fi first, where the browser can tell, and no more is asked for once 1.5 MB came, both as for the photos going up
// (attachments.ts); nor once 20 seconds went by, as on a slow line even a few hold the sync's lock for minutes, and a
// record saved meanwhile waits behind it. The rest come at the next sync, 30 s later. A shop's faces come once, some
// 150 KB each.
//
// In the page's sync alone, never the service worker's push: the pull brings the rows, and only a page pulls. A photo
// is fetched before the transaction that keeps it, on purpose: a Dexie transaction ends at the first wait on anything
// but the database.
import { ApiRefusal, NoConnection } from "@/api/refusal";

import { imageTypeOf, LARGEST_PHOTO } from "../attachments";
import type { ShopDatabase, StaffPhotoRow } from "../db";
import { isAboutTheDevice, syncAnswer, syncCallLimit } from "./answer";
import { MOST_BYTES, onCostlyLine, waitAfter, waitIsOver } from "./attachments";
import type { SyncPlace } from "./place";

/** The refusals about one photo, never the line or the server: no row names it any more, its file went as the row was
 * read, or hasn't come yet (which no worker's photo meets today, as its row and its file are kept together: PPL-9).
 * Asked by the code, not the status: a 404 of another code (`not_found`) is a server with no such route, one older than
 * this app, and stops the round. */
const ABOUT_THE_PHOTO = new Set([
  "attachment.not_found",
  "attachment.file_removed",
  "attachment.file_waiting",
]);

/** How long a sync goes on asking for photos: past it, the one on its way is the round's last. A limit in bytes alone is
 * none in time (PPL-14's review): 1.5 MB on an evening line of 10 KB a second is two and a half minutes of the sync's
 * lock, and Asha's clock-in, or the owner's suspension of Juma, waits behind pictures. */
export const LONGEST_ROUND_MS = 20_000;

/** The photos asked for and not kept, by id: how many tries, and until when each waits, on this laptop's clock in ms. */
const waits = new Map<string, { tries: number; until: number }>();

/** What came back for one photo: the photo; or none, and whether that is about this photo alone. */
type Heard = { photo: StaffPhotoRow } | { photo: null; aloneInThis: boolean };

/**
 * Drops the photos no staff row names, then asks for those it lacks, one at a time, unless the device is on a costly
 * line. A block or a "not registered" is kept (answer.ts) and thrown on; any other failure only ends the round, as the
 * next sync tries again.
 */
export async function fetchStaffPhotos(
  db: ShopDatabase,
  place: SyncPlace,
): Promise<void> {
  const lacking = await dropThenFindLacking(db);
  // The waits of photos no longer lacking say nothing any more, and would pile up for as long as the page is open.
  for (const id of waits.keys()) if (!lacking.has(id)) waits.delete(id);
  let cameBytes = 0;
  const startedAt = Date.now();
  for (const id of lacking) {
    // Asked before each photo: a device that leaves the shop's Wi-Fi for mobile data mid-round stops at once. Waiting
    // for Wi-Fi is no failed try.
    if (onCostlyLine()) return;
    // A photo's size is known only once it is here, so the share is counted after: one photo may pass it, by less than
    // the largest a photo may be.
    if (cameBytes >= MOST_BYTES) return;
    if (Date.now() - startedAt >= LONGEST_ROUND_MS) return;
    const waiting = waits.get(id);
    if (!waitIsOver(waiting?.until ?? null)) continue;
    // Its wait first, counted from when it is asked for, as a photo going up does, and taken back once it is kept. So
    // whatever goes wrong below, it waits: one that came and couldn't be kept too, as on a disk too full for it, which
    // throws out of here. With no wait it would come down again at every sync, and the ones after it never (PPL-14's
    // review).
    const tries = (waiting?.tries ?? 0) + 1;
    waits.set(id, { tries, until: Date.now() + waitAfter(tries) });
    const heard = await ask(id, place);
    if (heard.photo !== null) {
      cameBytes += heard.photo.bytes.byteLength;
      await keep(db, heard.photo);
      waits.delete(id);
    } else if (!heard.aloneInThis) return;
  }
}

/** Drops the photos no row names, and gives the ids of those the rows name that aren't here. In one transaction, so
 * the rows and the photos are seen as they stood together: a bootstrap empties the staff list and fills it again in a
 * transaction of its own, and read in between, the empty list would throw every face away. */
async function dropThenFindLacking(db: ShopDatabase): Promise<Set<string>> {
  return db.transaction("rw", [db.staff, db.staff_photos], async () => {
    const named = new Set<string>();
    // Asked as it is, not `!== null`: a row saved before rows named photos holds no `photo` at all, whatever its type
    // says (PPL-14).
    await db.staff.each(({ photo }) => {
      if (photo) named.add(photo);
    });
    const here = await db.staff_photos.toCollection().primaryKeys();
    await db.staff_photos.bulkDelete(here.filter((id) => !named.has(id)));
    for (const id of here) named.delete(id);
    return named;
  });
}

/** Keeps a photo that came, if a row still names it. Where the browser has the sync's lock, as the shop's do (lock.ts),
 * no pull can change a row meanwhile; in one without it, two tabs sync at once, and the other's pull may have. */
async function keep(db: ShopDatabase, photo: StaffPhotoRow): Promise<void> {
  await db.transaction("rw", [db.staff, db.staff_photos], async () => {
    const naming = await db.staff
      .filter((person) => person.photo === photo.id)
      .count();
    if (naming > 0) await db.staff_photos.put(photo);
  });
}

// One photo from the server, and what came back.
async function ask(id: string, place: SyncPlace): Promise<Heard> {
  try {
    const bytes = await syncAnswer(
      place.api.GET("/api/sync/v1/staff-photos/{id}/", {
        params: { path: { id } },
        // The file's bytes as they are, not read as JSON.
        parseAs: "arrayBuffer",
        signal: syncCallLimit(),
      }),
      place.hear,
    );
    // Undefined for an answer with no body at all (Content-Length: 0), whatever the type says.
    const type = bytes ? imageTypeOf(new Uint8Array(bytes)) : null;
    if (type === null || bytes.byteLength > LARGEST_PHOTO)
      return { photo: null, aloneInThis: false };
    // Its type by its first bytes, as the server knows it (CTRL-3), never by what the answer calls it.
    return { photo: { id, content_type: type, bytes } };
  } catch (error) {
    if (error instanceof NoConnection)
      return { photo: null, aloneInThis: false };
    // Blocked, or a key that opens no device: kept by syncAnswer, and thrown on, so the sync asks nothing more.
    if (error instanceof ApiRefusal && !isAboutTheDevice(error))
      return {
        photo: null,
        aloneInThis: ABOUT_THE_PHOTO.has(error.body.code),
      };
    throw error;
  }
}
