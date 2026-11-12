// outbox.ts — saving a document on this laptop (SYNC-8, 03 §6.2): the document, its number and its
// outbox row, written in one transaction.
//
// A counter screen never sends anything itself. It saves here and is done at once, online or offline;
// the push (sync/push.ts) takes what waits in the outbox to the server later, in number order. Nothing is
// lost on the way: a row leaves the outbox only once the server has accepted its document.
import { newId } from "@/lib/ids";

import type { DocumentRow, PendingEffectRow, ShopDatabase } from "./db";
import { LAST_DEVICE_SEQ, readLastDeviceSeq } from "./sync/meta";

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
  // The laptop's own clock, with its zone (`Z`), as every time a laptop sends must name it (ATT-1).
  const made: DocumentRow = {
    ...draft,
    id: newId(),
    client_time: new Date().toISOString(),
  };
  return db.transaction(
    "rw",
    [db.meta, db.documents, db.outbox, db.pending_effects],
    async () => {
      const last = await readLastDeviceSeq(db);
      if (last === null) throw new NeverFilled();
      const device_seq = last + 1;
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
}
