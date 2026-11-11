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

/** One of the laptop's own notes, by name: the pull cursor, the server-time offset, the next
 * device_seq, a receipt counter (03 §6.1). Each card that keeps a note names its key. */
export interface MetaRow {
  key: string;
  value: string | number;
}

/** An offline PIN check value this device made itself at a person's online login (SYNC-10, 03 §5.9).
 * Never the server's PIN hash: nothing secret syncs. */
export interface PinCheckRow {
  staff_id: string;
  salt: string;
  check: string;
  /** The person's pin_changed_at when the value was made: a newer one on their staff row drops it. */
  pin_changed_at: string;
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
  /** The shop's change number the server gave it when it was accepted. */
  posted_seq: number;
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
      // A rule's rows are looked up by the rule's name (get_setting's order, SYNC-7).
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
