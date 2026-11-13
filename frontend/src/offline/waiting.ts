// waiting.ts — the outbox rows still waiting to be sent, in their number order (SYNC-8, 03 §6.2).
//
// Its own file, with nothing but Dexie, so the service worker can read the outbox too (SYNC-16): outbox.ts,
// where the save lives, brings React's live queries and the page's device copy with it, which a worker
// has no use for, and whose `window` TypeScript refuses in the worker's code (tsconfig.sw.json).
import Dexie from "dexie";

import type { ShopDatabase } from "./db";

/** The outbox rows still waiting, in their number order, through the index made for it (db.ts): what the
 * push sends next (push.ts), what Tuma sasa counts (SYNC-11), and what the service worker looks for
 * before it pushes (SYNC-16). A row set aside is left out: it reached the server already, as refused.
 * Kept apart from push.ts: the push calls the server, and a counter screen that imported it would bring
 * the API client with it (rule 5). */
export function waitingInOrder(db: ShopDatabase) {
  return db.outbox
    .where("[status+device_seq]")
    .between(["waiting", Dexie.minKey], ["waiting", Dexie.maxKey]);
}
