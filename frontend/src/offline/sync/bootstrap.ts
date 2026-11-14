// bootstrap.ts — a laptop's first full copy of its shop's lists (SYNC-7, 03 §6.4).
//
// A laptop just registered holds nothing: no sides, no staff, no rules, so no counter screen can work.
// The bootstrap asks for everything at once, `GET /api/sync/v1/bootstrap/`, with the cursor that copy is
// valid at, and saves it all. From then on, pulls bring only what changed after that cursor (pull.ts).
// The answer also says where the laptop's own count stands, so its next record carries on from there,
// never from 1 again (SYNC-8).
//
// The server reads its cursor first and then the lists, so the lists may already hold a change numbered
// after it. That change comes again in the first pull, which saves the record as it is then: nothing is
// lost, and a record saved twice is still one record.
//
// The answer names its shop, and only that shop's database is filled; and the lowest app number the
// server serves, so an app below it fills nothing and updates first (SYNC-13).
import { api } from "@/api/client";
import { APP_NUMBER } from "@/lib/version";

import { databaseName, type ShopDatabase } from "../db";
import { dropOutdatedChecks } from "../pin";
import { syncAnswer, syncCallLimit } from "./answer";
import { keepOnThisPage } from "./page-place";
import { AppTooOld } from "./pull";
import { CURSOR, LAST_DEVICE_SEQ, readCursor, readLastDeviceSeq } from "./meta";

/** The server's copy is of another shop than this database's: the laptop was paired to another shop
 * since it last learned its own. Not the server's answer to a bad ask, and nothing the shop can put right,
 * so the console says it (triggers.tsx). */
export class WrongShop extends Error {
  constructor(answerShop: string, database: string) {
    super(`A copy of shop ${answerShop} for the database ${database}.`);
    this.name = "WrongShop";
  }
}

/** Whether this database still needs a copy: it has no cursor yet, or no number of its own. A laptop
 * filled before the bootstrap named its last number (SYNC-7's) has a cursor but no number, and could
 * never save a document (outbox.ts): it is filled again, once, which is safe, as a bootstrap empties
 * each list before it fills it and keeps the larger number. */
export async function needsBootstrap(db: ShopDatabase): Promise<boolean> {
  return (
    (await readCursor(db)) === null || (await readLastDeviceSeq(db)) === null
  );
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
 *
 * An app below the server's lowest app number is thrown too (AppTooOld, as a pull throws it), and
 * changes nothing: the sync tells it, and the app updates first (too-old.ts). An old tab's sync can reach
 * the bootstrap before its update, after a release whose new database version removed the cursor to fill
 * again; the old code has no drawer for the list that release added, and would set the cursor past its
 * lines for good.
 *
 * A copy of another shop is thrown too (WrongShop), and changes nothing. The answer is the shop of the
 * device key the browser sends now; this database is the shop the device's saved copy names (mpc.device,
 * perhaps from an earlier visit). A laptop paired to another shop between that copy and this call would
 * otherwise write the new shop's lists into the old shop's database, and its counter would show the wrong
 * shop's staff and rules. Pairing a working laptop again is refused (pairing.already_paired, 03 §5.9),
 * which makes that moment rare. The device check's next answer brings the new shop, whose own database
 * then fills.
 */
export async function bootstrap(db: ShopDatabase): Promise<void> {
  const copy = await syncAnswer(
    api.GET("/api/sync/v1/bootstrap/", { signal: syncCallLimit() }),
    keepOnThisPage,
  );
  // Before the transaction: a copy for another shop writes nothing at all. Each database is named by its
  // shop's id (db.ts), so the name says whose it is.
  if (databaseName(copy.shop) !== db.name)
    throw new WrongShop(copy.shop, db.name);
  if (copy.min_app_version > APP_NUMBER)
    throw new AppTooOld(
      `The server serves app number ${copy.min_app_version} and up; this app is ${APP_NUMBER}.`,
    );

  await db.transaction(
    "rw",
    [
      db.side,
      db.payment_account,
      db.staff,
      db.setting,
      db.setting_keys,
      db.meta,
      db.pin_checks,
    ],
    async () => {
      // One line per list, by the list's code, which is also its drawer's name (db.ts).
      await db.side.clear();
      await db.side.bulkPut(copy.side);
      await db.payment_account.clear();
      await db.payment_account.bulkPut(copy.payment_account);
      await db.staff.clear();
      await db.staff.bulkPut(copy.staff);
      // The laptop's own checks aren't emptied with the lists: a person whose PIN is the same keeps
      // logging in offline. Only those the new copy no longer matches go (SYNC-10).
      await dropOutdatedChecks(db);
      await db.setting.clear();
      await db.setting.bulkPut(copy.setting);
      await db.setting_keys.clear();
      await db.setting_keys.bulkPut(copy.setting_keys);
      // The laptop's own count: the server's, unless this laptop is ahead of it. Filled again (SYNC-13)
      // with records still waiting in its outbox, it has numbered past what the server has seen, and the
      // server's number would hand one of them out a second time.
      const mine = (await readLastDeviceSeq(db)) ?? 0;
      await db.meta.put({
        key: LAST_DEVICE_SEQ,
        value: Math.max(mine, copy.last_device_seq),
      });
      // Last, inside the same transaction: the cursor says the copy is whole.
      await db.meta.put({ key: CURSOR, value: copy.cursor });
    },
  );
}
