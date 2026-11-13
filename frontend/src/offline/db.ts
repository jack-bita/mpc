// db.ts — the device database: one IndexedDB database per shop on this device, opened with Dexie
// (SYNC-6, 03 §6.1).
//
// It owns the list of drawers (Dexie calls them tables) and their versions. Every offline card reads
// and writes through it: the pull fills the server's drawers (SYNC-7), saveDocument() writes a document
// and its outbox row (SYNC-8), and the offline PIN check keeps its values here (SYNC-10).
//
// One database per shop, named after the shop's id, so the practice shop or the demo never mixes with
// the live shop on one laptop. Which shop this device belongs to lives outside, in mpc.device
// (src/features/devices/this-device.ts): the shop must be known before its database can be opened,
// and meta keeps no copy of it.
//
// A change to the drawers is a new version at the end of VERSIONS, with an upgrade if old rows must
// change. An old version is never edited: a laptop already on it, full of unsent sales, could no longer
// move up. The same idea as a Django migration once it is on main.
import Dexie, { type EntityTable, type Transaction } from "dexie";

import type { components } from "@/api/schema";

// The shapes the server sends (SYNC-2): its drawers keep each record exactly as it came.
type Schemas = components["schemas"];

/** One of the laptop's own notes, by name: the pull cursor, the server-time offset, the last server
 * time seen, the last record's number, a receipt counter (03 §6.1). Each card that keeps a note names
 * its key (sync/meta.ts). A reset of this database wipes the record number too, so it must never start
 * the count again from 1: the bootstrap that fills it again brings back the server's (SYNC-8). */
export interface MetaRow {
  key: string;
  value: string | number;
}

/** An offline PIN check value this device made itself at a person's online login (SYNC-10, 03 §5.9).
 * Never the server's PIN hash: nothing secret syncs. Its rules live in pin.ts. None of these fields is a
 * search key, so adding one needs no new version. */
export interface PinCheckRow {
  staff_id: string;
  /** 16 random bytes, as hex, made on this laptop for this one check. Not a secret: the check needs it
   * again offline. It makes two people with the same PIN, or one PIN on two laptops, give different
   * checks, so no list made in advance fits them. */
  salt: string;
  /** PBKDF2 with SHA-256 of the PIN and the salt: 32 bytes, as hex. */
  check: string;
  /** How many turns of the blender made it. The check is read with the same number, so a later app
   * that makes new checks with more still reads the old ones. */
  iterations: number;
  /** The person's pin_changed_at when the value was made: a different one on their staff row drops it.
   * Null if their row on the laptop said no PIN yet: a row behind the server's, which the next sync
   * brings up to date, and the check with it. */
  pin_changed_at: string | null;
  /** Wrong tries since the last lock or right PIN, each counted before its check (pin.ts). */
  wrong_tries: number;
  /** How long the next lock lasts, in minutes: 1, then twice as long after each lock, up to 60. */
  next_lock_minutes: number;
  /** Until when, on this laptop's clock in ms, the person is locked here; null when they aren't. */
  locked_until: number | null;
}

/** A document made on this device: a clock-in now, a sale or a repayment later (03 §6.1). It holds
 * the push's envelope (03 §6.3) but its place in the line, device_seq, which its outbox row keeps. */
export interface DocumentRow {
  /** A UUIDv7 made here, so the server knows a resend as the same document (SYNC-4). */
  id: string;
  type: string;
  schema_version: number;
  /** This laptop's clock when it was made, with its zone (`Z`), as the push sends it (ATT-1). */
  client_time: string;
  /** The staff member who made it: the server checks they were working then (SYNC-5). */
  created_by: string;
  /** What the document says, in its type's shape. */
  payload: unknown;
  /** Only on a record a rescue file carried here from another laptop of the shop (SYNC-12, 03 §6.7): where
   * it was made and who loaded the file. The push sends it, so the server checks the record against the
   * laptop that made it. Not a search key, so adding it needs no new version. */
  carried_from?: CarriedFrom;
}

/** Where a carried record was made: the laptop, its number there, and the staff member who loaded the
 * rescue file on this laptop (the push's CarriedEnvelope). */
export interface CarriedFrom {
  device: string;
  device_seq: number;
  loaded_by: string;
}

/** One document not yet accepted (SYNC-8, 03 §6.2). Only unsent ones: an accepted document leaves
 * the outbox, with its posted_seq, for sent_archive, in one transaction, so a push can never send an
 * accepted one again as if it were waiting. The document itself stays in documents, for the screens. */
export interface OutboxRow {
  /** The document's own id: one outbox row per document. */
  id: string;
  type: string;
  /** Its place in the line: documents leave in this order, and no two share a number. */
  device_seq: number;
  /** Waiting to go, or set aside after an `invalid` answer for someone to look at. */
  status: "waiting" | "needs_attention";
  attempts: number;
  last_error: string | null;
}

/** A stock or balance change of a document the server hasn't confirmed yet, so screens count it
 * (03 §6.1). The sale and payment cards add what it changes and by how much. */
export interface PendingEffectRow {
  id: string;
  document_id: string;
  /** Its document's posted_seq, copied here when the document is accepted; null until then. Once the
   * pull's cursor reaches it, the server's own numbers include the change, so the row goes (sync rules). */
  posted_seq: number | null;
}

/** A document already sent, kept 30 days so it can be sent again after a server restore (03 §6.1). */
export interface SentDocumentRow extends DocumentRow {
  /** Its place in the line, from its outbox row, which is gone by now: a replay resends in this
   * order, as every push must (03 §6.3). */
  device_seq: number;
  sent_at: string;
  /** The shop's change number the server gave it when it was accepted: null when its save changed
   * nothing a laptop keeps a copy of (PushedDocument.posted_seq). Not a search key, so allowing null
   * needs no new version: only a drawer's name or its search keys do. */
  posted_seq: number | null;
}

/** One step in the database's life: its number, its drawers, and an upgrade if old rows must change.
 * A drawer set to null is removed in that step. */
export interface Version {
  version: number;
  stores: Record<string, string | null>;
  upgrade?: (tx: Transaction) => Promise<void>;
}

/** Every version, in order. Add new ones at the end; never edit one already on main (sync rules). */
export const VERSIONS: readonly Version[] = [
  {
    version: 1,
    stores: {
      // The laptop's own notes, one per name.
      meta: "key",
      // What the server sends, one drawer per list of the bootstrap (SYNC-2), so a pull's `entity`
      // names its drawer (SYNC-7). Products, contacts and the rest come with their cards, as new versions.
      side: "id",
      payment_account: "id",
      staff: "id",
      // A rule's rows are looked up by the rule's name (get_setting's order, SYNC-7). Not by name and
      // side together: a shop-wide row's side is null, and IndexedDB leaves a row out of a search key
      // it can't sort, so every shop-wide rule would vanish from that search and its default win.
      setting: "id, key",
      setting_keys: "key",
      // One check value per person (SYNC-10).
      pin_checks: "staff_id",
      // Everything made here, of every type. By type, and by type and time together, so a screen
      // reads one kind for one day (today's clock-ins, SYNC-11) without reading every day before it.
      documents: "id, type, [type+client_time]",
      // One row per unsent document. Unique device_seq: one number, one document (SYNC-4).
      // By status and number together, so the push reads what is waiting already in its order, and
      // the needs-attention list what was set aside.
      outbox: "id, &device_seq, [status+device_seq]",
      // By their document, to stamp its posted_seq on them when it is accepted; by that number, so
      // each pull drops the ones its cursor has passed in one step. A row whose number is still null
      // is left out of that search key, as IndexedDB leaves out what it can't sort, so a document
      // the server hasn't accepted keeps its effects.
      pending_effects: "id, document_id, posted_seq",
      // By when it was sent, so rows past 30 days can be cleared; by number, so a replay after a
      // server restore resends them in their order (03 §6.7).
      sent_archive: "id, sent_at, device_seq",
    },
  },
];

/** Every drawer, typed: TypeScript knows the staff drawer holds staff rows, keyed by id. */
export type ShopDatabase = Dexie & {
  meta: EntityTable<MetaRow, "key">;
  side: EntityTable<Schemas["SideRecord"], "id">;
  payment_account: EntityTable<Schemas["PaymentAccountRecord"], "id">;
  staff: EntityTable<Schemas["StaffRecord"], "id">;
  setting: EntityTable<Schemas["SettingRecord"], "id">;
  setting_keys: EntityTable<Schemas["SettingKeyRecord"], "key">;
  pin_checks: EntityTable<PinCheckRow, "staff_id">;
  documents: EntityTable<DocumentRow, "id">;
  outbox: EntityTable<OutboxRow, "id">;
  pending_effects: EntityTable<PendingEffectRow, "id">;
  sent_archive: EntityTable<SentDocumentRow, "id">;
};

/** The database's name in the browser: one per shop, by the shop's id, which never changes. */
export function databaseName(shopId: string): string {
  return `mpc-shop-${shopId}`;
}

/** A shop's database on this device. Dexie opens it at its first read or write, building or
 * upgrading it then: a laptop on an older version runs each newer step's upgrade, once, in order.
 * `versions` is for tests only, which stack a pretend later version on top of the real ones. */
export function openShopDatabase(
  shopId: string,
  versions: readonly Version[] = VERSIONS,
): ShopDatabase {
  const db = new Dexie(databaseName(shopId)) as ShopDatabase;
  for (const step of versions) {
    const declared = db.version(step.version).stores(step.stores);
    if (step.upgrade) declared.upgrade(step.upgrade);
  }
  return db;
}
