// outbox.ts — the laptop's outbox (SYNC-8, 03 §6.2): saving a document, with its number and its outbox
// row, in one transaction; and the live list of the records the server refused, set aside.
//
// A counter screen never sends anything itself. It saves here and is done at once, online or offline;
// the push (sync/push.ts) takes what waits in the outbox to the server later, in number order: 2 s after
// the save, as the save tells the sync's moments (sync/asks.ts, SYNC-9). Nothing is lost on the way: a
// row leaves the outbox only once the server has accepted its document, and a record the server refused
// stays in it, set aside, for someone to look at.
import Dexie from "dexie";
import { useLiveQuery } from "dexie-react-hooks";

import { newId } from "@/lib/ids";

import type { DocumentRow, PendingEffectRow, ShopDatabase } from "./db";
import { tellRecordSaved } from "./sync/asks";
import { LAST_DEVICE_SEQ, readLastDeviceSeq } from "./sync/meta";
import { useShopDatabase } from "./this-shop";

/** What a screen hands over to save: the document without what the save fills in, its id and its time. */
export type Draft = Omit<DocumentRow, "id" | "client_time">;

/** A stock or balance change of the document, as a screen hands it over. Nothing yet: the sale and
 * payment cards add what it changes and by how much. Its id, document and posted_seq are filled in here. */
export type EffectDraft = Omit<
  PendingEffectRow,
  "id" | "document_id" | "posted_seq"
>;

/** The document as saved, with its place in the line. */
export type SavedDocument = DocumentRow & { device_seq: number };

/** Refused: this laptop has had no bootstrap yet, so it doesn't know where its count stands. Counting
 * from 1 could hand out a number it already used before a wipe (SYNC-5's note). */
export class NeverFilled extends Error {
  constructor() {
    super(
      "This laptop has had no bootstrap yet, so it can't number a document.",
    );
    this.name = "NeverFilled";
  }
}

/** Refused: a draft the server would refuse with the whole push (PushedEnvelope, a 400). Saved, it would
 * stop every push after it, for good; a bug in the screen that made it, so it fails at the counter. */
export class BrokenDraft extends Error {
  constructor(readonly field: string) {
    super(`The draft's ${field} is not one the push can send.`);
    this.name = "BrokenDraft";
  }
}

// The server's limits on an envelope (apps/sync/api/serializers.py, PushedEnvelope; apps/sync/push.py).
const LONGEST_TYPE = 40;
const HIGHEST_SCHEMA_VERSION = 2 ** 31 - 1;
const HIGHEST_DEVICE_SEQ = 10 ** 12 - 2;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

// The parts a screen hands over, checked as the server will check them. The payload must be a plain
// object, as the server reads it as one (a DictField): a list, a date or a string is refused.
function checkDraft(draft: Draft): void {
  if (draft.type.length === 0 || draft.type.length > LONGEST_TYPE)
    throw new BrokenDraft("type");
  if (
    !Number.isInteger(draft.schema_version) ||
    draft.schema_version < 1 ||
    draft.schema_version > HIGHEST_SCHEMA_VERSION
  )
    throw new BrokenDraft("schema_version");
  if (!UUID.test(draft.created_by)) throw new BrokenDraft("created_by");
  const { payload } = draft;
  if (
    typeof payload !== "object" ||
    payload === null ||
    Object.getPrototypeOf(payload) !== Object.prototype
  )
    throw new BrokenDraft("payload");
}

/**
 * Saves a document made on this laptop, ready for the push: the document, the next number, its outbox
 * row and its pending effects, in one transaction (03 §6.2). Either all of it lands, or none of it does:
 * a document saved without its outbox row would never be sent, and a number taken without its document
 * would be a gap the server flags (SYNC-5).
 *
 * The number is read inside the transaction. Two saves at once, from two tabs, then take turns, as a
 * transaction that writes a drawer waits for the one before it: the second reads the number the first
 * left, never the same one.
 */
export async function saveDocument(
  db: ShopDatabase,
  draft: Draft,
  effects: readonly EffectDraft[] = [],
): Promise<SavedDocument> {
  checkDraft(draft);
  // The laptop's own clock, with its zone (`Z`), as every time a laptop sends must name it (ATT-1).
  const made: DocumentRow = {
    ...draft,
    id: newId(),
    client_time: new Date().toISOString(),
  };
  const saved = await db.transaction(
    "rw",
    [db.meta, db.documents, db.outbox, db.pending_effects],
    async () => {
      const last = await readLastDeviceSeq(db);
      if (last === null) throw new NeverFilled();
      const device_seq = last + 1;
      // Far past any laptop's life, but a number the server refuses would stop every push after it.
      if (device_seq > HIGHEST_DEVICE_SEQ) throw new BrokenDraft("device_seq");
      await db.documents.add(made);
      await db.outbox.add({
        id: made.id,
        type: made.type,
        device_seq,
        status: "waiting",
        attempts: 0,
        last_error: null,
      });
      await db.meta.put({ key: LAST_DEVICE_SEQ, value: device_seq });
      // Not posted yet: the push stamps the document's posted_seq on them once it is accepted, and the
      // pull drops them once its cursor passes it (SYNC-7).
      if (effects.length > 0) {
        await db.pending_effects.bulkAdd(
          effects.map((effect) => ({
            ...effect,
            id: newId(),
            document_id: made.id,
            posted_seq: null,
          })),
        );
      }
      return { ...made, device_seq };
    },
  );
  // Only once the transaction is in: a sync told sooner could push before the record is there to find.
  tellRecordSaved();
  return saved;
}

/** A record the server refused (`invalid`), set aside by the push: its document, its number, and the
 * server's reason, an error code (`document.type_unknown`). */
export interface SetAside {
  document: DocumentRow;
  device_seq: number;
  reason: string;
}

/**
 * The records set aside on this laptop, in their number order, read live: the list redraws by itself
 * when a push sets one more aside. Undefined while its first read runs, or while the device isn't
 * registered. No screen shows it yet: SYNC-11 does, with words of its own for each reason, as the
 * office's sentence for `id.taken` ("Try again.") is wrong here: a resend gets the same answer.
 */
export function useNeedsAttention(): SetAside[] | undefined {
  const db = useShopDatabase();
  return useLiveQuery(async () => {
    if (db === null) return undefined;
    // One read transaction, so the rows and their documents are seen as they stood together.
    return db.transaction("r", [db.outbox, db.documents], async () => {
      const rows = await db.outbox
        .where("[status+device_seq]")
        .between(
          ["needs_attention", Dexie.minKey],
          ["needs_attention", Dexie.maxKey],
        )
        .toArray();
      const documents = await db.documents.bulkGet(rows.map((row) => row.id));
      return rows.map((row, i) => {
        const document = documents[i];
        // Written in one transaction with its row (saveDocument), so never missing.
        if (document === undefined)
          throw new Error(`Outbox row ${row.id} has no document.`);
        return {
          document,
          device_seq: row.device_seq,
          reason: row.last_error ?? "",
        };
      });
    });
  }, [db]);
}
