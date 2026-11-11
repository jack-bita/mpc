// pull.ts — brings what changed on the server since the laptop's cursor, a page at a time, into the
// shop's database (SYNC-7, 03 §6.4).
//
// The server numbers every change in its shop's log, in commit order. The laptop keeps the last number
// it holds, the cursor, and asks `GET /api/sync/v1/pull/?cursor=N` for the changes after it. Each page
// is applied in one Dexie transaction, together with the new cursor: a tab closed in the middle of a page
// undoes the whole page, the cursor stays where it was, and the next pull asks for the same page again.
// So no change is ever skipped, and a change applied twice is harmless, as each line carries the record
// as it is now.
import type { EntityTable, IDType } from "dexie";

import { api } from "@/api/client";
import type { components } from "@/api/schema";

import type { ShopDatabase } from "../db";
import { syncAnswer } from "./answer";
import { CLOCK_OFFSET, CURSOR, LAST_SERVER_TIME, readCursor } from "./meta";

type Change = components["schemas"]["Change"];
type Page = components["schemas"]["PullAnswer"];

/** The lists a pull can change, by the code a change names in `entity`, which is its drawer's name too
 * (db.ts). A list the server adds later comes with its card, here and as a new database version. */
const LISTS = ["side", "payment_account", "staff", "setting"] as const;

/**
 * A page named a list this app has no drawer for: the server is newer than the app. The pull stops
 * before that page, so its changes are never passed over: once the app updates, the same page comes
 * again (SYNC-13's note). Moving the cursor past it would lose those records on this laptop for good.
 */
export class AppTooOld extends Error {
  constructor(readonly entity: string) {
    super(`No drawer for the list "${entity}".`);
    this.name = "AppTooOld";
  }
}

/**
 * Pulls until the server says no more changes wait. Each page is asked for, then applied whole.
 *
 * It needs a cursor, so a laptop is bootstrapped first (bootstrap.ts): a pull from 0 would miss the
 * rules' defaults and any record saved without a line in the log (SYNC-3's note).
 *
 * A refusal or a lost network stops it there, thrown on: the pages already applied stay, with their
 * cursor, and the next pull goes on from it. A block or a "not registered" is kept on the way
 * (answer.ts).
 */
export async function pull(db: ShopDatabase): Promise<void> {
  const start = await readCursor(db);
  if (start === null) throw new Error("Bootstrap this database first.");
  let cursor: number = start;

  for (;;) {
    // The laptop's clock before and after the call: the server's time was read somewhere between, so the
    // middle is the best guess of when, on this laptop's clock (03 §6.6).
    const askedAt = Date.now();
    const page: Page = await syncAnswer(
      api.GET("/api/sync/v1/pull/", { params: { query: { cursor } } }),
    );
    const answeredAt = Date.now();

    checkPage(page);
    await applyPage(db, page, (askedAt + answeredAt) / 2);
    cursor = page.cursor;

    // Only the server knows whether more wait: a page passes over the lines of lists no laptop keeps,
    // so a short page, or an empty one, can still have more after it. Never count the changes.
    if (!page.has_more) return;
  }
}

// Every change on the page is one the app can apply, or nothing is: checked before the transaction, so
// a page the app can't read changes nothing at all.
function checkPage(page: Page): void {
  for (const change of page.changes) {
    if (!(LISTS as readonly string[]).includes(change.entity))
      throw new AppTooOld(change.entity);
    // An upsert brings the record as it is now. One with none is not a page this app understands.
    if (change.op === "upsert" && change.data === null)
      throw new Error(`Change ${change.seq} has no record.`);
  }
}

/** One page, whole, in one transaction: its changes in order, then the cursor and the clock. */
async function applyPage(
  db: ShopDatabase,
  page: Page,
  laptopTime: number,
): Promise<void> {
  await db.transaction(
    "rw",
    [
      db.side,
      db.payment_account,
      db.staff,
      db.setting,
      db.meta,
      db.pending_effects,
    ],
    async () => {
      // In order: a record may come on several lines of one page, each as it was then, and the last
      // line is how it is now.
      for (const change of page.changes) await applyChange(db, change);

      await db.meta.bulkPut([
        { key: CURSOR, value: page.cursor },
        // How far the server's clock is ahead of this laptop's, kept from every page, an empty one too.
        {
          key: CLOCK_OFFSET,
          value: Date.parse(page.server_time) - laptopTime,
        },
        { key: LAST_SERVER_TIME, value: page.server_time },
      ]);

      // No double counting (03 §6.4): the server's numbers now include every document posted up to the
      // cursor, so that document's pending effects would count it a second time. A row whose document
      // isn't accepted yet has posted_seq null, which IndexedDB leaves out of the search key, so it stays.
      await db.pending_effects
        .where("posted_seq")
        .belowOrEqual(page.cursor)
        .delete();
    },
  );
}

// The switch tells TypeScript which drawer each change's record belongs in: a staff change's data is a
// staff record, and so on.
function applyChange(db: ShopDatabase, change: Change): Promise<unknown> {
  switch (change.entity) {
    case "side":
      return applyTo(db.side, change);
    case "payment_account":
      return applyTo(db.payment_account, change);
    case "staff":
      return applyTo(db.staff, change);
    case "setting":
      return applyTo(db.setting, change);
  }
}

/** An upsert saves the record as it is now, new or changed. An archive takes it off the laptop's list:
 * a person who left, a side closed. An archive of a record this laptop never had does nothing. */
function applyTo<R extends { id: string }>(
  table: EntityTable<R, "id">,
  change: { id: string; op: Change["op"]; data: R | null },
): Promise<unknown> {
  if (change.op === "upsert" && change.data !== null)
    return table.put(change.data);
  // Every list here is keyed by its id, a string; TypeScript can't see that through the generic R.
  return table.delete(change.id as IDType<R, "id">);
}
