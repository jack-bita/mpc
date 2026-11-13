// background.ts — the service worker's push: what waits in a shop's outbox goes when the network comes
// back, even with the app closed (SYNC-16, 03 §6.5).
//
// Background Sync is the browser's: the page asks it to wake the worker once the network is there, under
// a name that carries the shop's id (backgroundSyncTag). Chrome and
// Edge do it, on the phone and the laptops; Firefox and Safari don't, and carry on as before, with the
// open app's own moments (triggers.tsx).
//
// It keeps the page's rules, with the worker's own tools:
// - the same lock as the tabs (lock.ts), so a tab and the worker never push the same records at once;
// - the same wait after a failure (backoff.ts, through pushKeepingTheWait), kept in the database;
// - a block or a "not registered" is left as a note for the page (meta.ts, DEVICE_REFUSED), as the worker
//   has no localStorage; the page takes it as it opens (page-place.ts).
// It only pushes: getting the records out is the job, and the app pulls the office's changes as it opens.
//
// It imports nothing of the page's: TypeScript checks it with the worker's types (tsconfig.sw.json).
import type { ApiClient } from "@/api/make-client";

import { openShopDatabase } from "../db";
import { waitingInOrder } from "../waiting";
import { isAboutTheDevice } from "./answer";
import { mayPush } from "./backoff";
import { inTurn } from "./lock";
import { noteDeviceRefused, readDeviceRefused } from "./meta";
import { pushKeepingTheWait } from "./push";

const TAG_START = "mpc-sync-";

/** The name of a shop's background sync: the worker has no saved device (mpc.device lives in the
 * page's localStorage), so the name itself tells it which shop's database to send from. */
export function backgroundSyncTag(shopId: string): string {
  return `${TAG_START}${shopId}`;
}

/** The shop a background sync's name is for, or null for a name that isn't ours. */
export function shopOfTag(tag: string): string | null {
  return tag.startsWith(TAG_START) && tag.length > TAG_START.length
    ? tag.slice(TAG_START.length)
    : null;
}

/**
 * Thrown so the browser tries again later: a push that must wait, or the server said "try later". A
 * background sync whose work fails is tried again by the browser itself, a few times, further apart each
 * time; the open app's moments carry on meanwhile.
 */
export class TryLater extends Error {
  constructor(why: string) {
    super(`The background push will try again later: ${why}.`);
    this.name = "TryLater";
  }
}

/** What the worker hands in: its own client, whose CSRF token it reads its own way, and whether it has
 * a token at all. */
export interface WorkerTools {
  api: ApiClient;
  hasCsrfToken: () => Promise<boolean>;
}

/**
 * Pushes what waits in the shop's outbox. Ends quietly when there is nothing to do (nothing waits, the
 * page already sent it, or the device was refused); throws for the browser to try again later.
 */
export async function backgroundPush(
  shopId: string,
  tools: WorkerTools,
): Promise<void> {
  // Its own connection to the database: the worker shares no memory with the pages. Closed at the end,
  // as the browser may keep the worker alive a while, and an open connection would hold up an app
  // update's new database version.
  const db = openShopDatabase(shopId);
  try {
    await inTurn(shopId, async () => {
      // Refused already, and the page hasn't taken the note yet: asking again would only be refused.
      if ((await readDeviceRefused(db)) !== null) return;
      // Most often the open app sent it first (2 s after the save): then there is nothing to do. No empty
      // push either: the report it carries is the open app's to send (SYNC-14).
      if ((await waitingInOrder(db).count()) === 0) return;
      // A browser that lost its token: the push would be refused (403). The app gets one back as it
      // opens (DeviceMeView), and pushes then.
      if (!(await tools.hasCsrfToken())) throw new TryLater("no CSRF token");
      // The wait after a failure holds here too: a worker the browser woke is no one pressing Tuma sasa.
      if (!(await mayPush(db))) throw new TryLater("the push waits");
      const place = {
        api: tools.api,
        hear: (refusal: Parameters<typeof noteDeviceRefused>[1]) =>
          noteDeviceRefused(db, refusal),
      };
      let result;
      try {
        result = await pushKeepingTheWait(db, place);
      } catch (error) {
        // Blocked, or a key that opens no device: the note is left, and trying again can't help.
        if (isAboutTheDevice(error)) return;
        throw error;
      }
      if (result === "retry") throw new TryLater("the server said retry");
    });
  } finally {
    db.close();
  }
}
