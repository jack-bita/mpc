// bootstrap.ts — a laptop's first full copy of its shop's lists (SYNC-7, 03 §6.4).
//
// A laptop just registered holds nothing: no sides, no staff, no rules, so no counter screen can work.
// The bootstrap asks for everything at once, `GET /api/sync/v1/bootstrap/`, with the cursor that copy is
// valid at, and saves it all. From then on, pulls bring only what changed after that cursor (pull.ts).
//
// The server reads its cursor first and then the lists, so the lists may already hold a change numbered
// after it. That change comes again in the first pull, which saves the record as it is then: nothing is
// lost, and a record saved twice is still one record.
import { api } from "@/api/client";

import type { ShopDatabase } from "../db";
import { syncAnswer } from "./answer";
import { CURSOR, readCursor } from "./meta";

/** Whether this database still needs its first copy: it has no cursor yet. */
export async function needsBootstrap(db: ShopDatabase): Promise<boolean> {
  return (await readCursor(db)) === null;
}

/**
 * Fills the database with the shop's lists, as the server has them now, and sets the cursor.
 *
 * The answer is asked for before the transaction opens. A Dexie transaction ends by itself as soon as it
 * waits on anything but the database, so a network call inside it would end it halfway.
 *
 * Then every list and the cursor are written in one transaction: all of it lands, or none of it. A tab
 * closed halfway leaves a database with no cursor, which simply asks again, never a half copy that the
 * app would take as whole. Each list is emptied first, so a laptop filled again (after a reset, SYNC-13)
 * keeps no record the server no longer sends.
 *
 * A refusal is thrown, after keeping a block or a "not registered" (answer.ts), and changes nothing.
 */
export async function bootstrap(db: ShopDatabase): Promise<void> {
  const copy = await syncAnswer(api.GET("/api/sync/v1/bootstrap/"));

  await db.transaction(
    "rw",
    [
      db.side,
      db.payment_account,
      db.staff,
      db.setting,
      db.setting_keys,
      db.meta,
    ],
    async () => {
      // One line per list, by the list's code, which is also its drawer's name (db.ts).
      await db.side.clear();
      await db.side.bulkPut(copy.side);
      await db.payment_account.clear();
      await db.payment_account.bulkPut(copy.payment_account);
      await db.staff.clear();
      await db.staff.bulkPut(copy.staff);
      await db.setting.clear();
      await db.setting.bulkPut(copy.setting);
      await db.setting_keys.clear();
      await db.setting_keys.bulkPut(copy.setting_keys);
      // Last, inside the same transaction: the cursor says the copy is whole.
      await db.meta.put({ key: CURSOR, value: copy.cursor });
    },
  );
}
