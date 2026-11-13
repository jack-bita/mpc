// push.ts — sends the outbox to the server, in number order, and reads each answer (SYNC-8, 03 §6.3).
//
// A counter screen saves a document and its outbox row (outbox.ts) and is done. At each sync this file
// takes what waits, up to 100 at a time, to `POST /api/sync/v1/push/`, and reads the server's answers,
// one per document, in the order sent:
//
//   accepted   → the row leaves the outbox for sent_archive, with the server's posted_seq; the
//                document's pending effects get that posted_seq too, and the pull drops them later
//                (none when its save changed nothing a laptop keeps: its effects go at once)
//   invalid    → the row is set aside as needs_attention, with its reason, and its pending effects go,
//                as the server saved nothing of it; the rest go on
//   duplicate  → sent before, its answer lost on the way back: read as that first answer
//   retry      → the server had trouble saving it: the push stops, and it and the rest wait
//
// Each push also carries the laptop's report on itself (SYNC-5): its clock as it sends, its version,
// and how many records still wait. With nothing waiting, an empty push still goes, so the office sees
// the laptop is alive (SYNC-14).
import { api } from "@/api/client";
import { ApiRefusal } from "@/api/refusal";
import type { components } from "@/api/schema";
import { APP_VERSION } from "@/lib/version";

import type { DocumentRow, OutboxRow, ShopDatabase } from "../db";
import { waitingInOrder } from "../outbox";
import { syncAnswer, syncCallLimit } from "./answer";

type Envelope = components["schemas"]["PushedEnvelopeRequest"];
type PushedAnswer = components["schemas"]["PushedAnswer"];

/** At most this many documents a push, as the server takes (MOST_DOCUMENTS, 03 §6.3): one push stays
 * short on a shop's slow line. */
export const MOST_DOCUMENTS = 100;

/** How a push ended: every record sent got an answer that settles it, or the server said to try later. */
export type PushResult = "sent" | "retry";

/**
 * The server refused a push as broken (400: an envelope or the report it can't read). A bug in this
 * code, never one record to set aside: every later push would be refused the same way. Thrown as no
 * answer of the server's, so the sync's failure report puts it in the console (reportSyncFailure),
 * where the refused fields name what broke (`documents.0.device_seq`).
 */
export class BrokenPush extends Error {
  constructor(readonly refusal: ApiRefusal) {
    super(
      `The server refused the push as broken: ${JSON.stringify(refusal.body.fields)}`,
    );
    this.name = "BrokenPush";
  }
}

/** One record to send: its outbox row, which holds its number, and its document. */
interface Waiting {
  row: OutboxRow;
  document: DocumentRow;
}

/**
 * Sends what waits in the outbox, a batch at a time, until a batch that wasn't full (nothing more
 * waited when it was read) or a retry. A record saved while a push runs goes at the next sync.
 *
 * A refusal or a lost network is thrown on, and the outbox is left as it is: every record still waits,
 * and the next push sends it again, which is safe, as the server knows a record by its id (SYNC-4). A
 * block or a "not registered" is kept on the way (answer.ts); an unblock brings back the same key, so
 * the records can still arrive (03 §5.9, step 4). A 400 (a broken envelope) is a bug in this code, never
 * one record to set aside: it is thrown as a BrokenPush.
 */
export async function push(db: ShopDatabase): Promise<PushResult> {
  for (;;) {
    const { batch, others } = await nextBatch(db);
    // Read afresh at each try: a retry sent with the first try's time would show the laptop's clock as
    // off by the wait, and every offline clock-in in it as unverified (ATT-1).
    const sentAt = new Date().toISOString();
    const { answers } = await syncAnswer(
      api.POST("/api/sync/v1/push/", {
        signal: syncCallLimit(),
        body: {
          documents: batch.map(envelope),
          sent_at: sentAt,
          app_version: APP_VERSION,
          unsent_count: others,
          // The offline periods, from SYNC-14 on.
          outages: [],
        },
      }),
    ).catch((error: unknown) => {
      if (error instanceof ApiRefusal && error.status === 400)
        throw new BrokenPush(error);
      throw error;
    });
    if (!(await applyAnswers(db, batch, answers, sentAt))) return "retry";
    if (batch.length < MOST_DOCUMENTS) return "sent";
  }
}

// The next batch and how many others wait, read together, in one transaction, so the count matches it.
async function nextBatch(
  db: ShopDatabase,
): Promise<{ batch: Waiting[]; others: number }> {
  return db.transaction("r", [db.outbox, db.documents], async () => {
    const rows = await waitingInOrder(db).limit(MOST_DOCUMENTS).toArray();
    // Only the waiting ones count as unsent: a record set aside is on the server already, as invalid,
    // with a flag, and counted it would hold up a drawer's approval for good (M8).
    const waiting = await waitingInOrder(db).count();
    const documents = await db.documents.bulkGet(rows.map((row) => row.id));
    const batch = rows.map((row, i) => {
      const document = documents[i];
      // Written in one transaction with its row (outbox.ts), so never missing.
      if (document === undefined)
        throw new Error(`Outbox row ${row.id} has no document.`);
      return { row, document };
    });
    return { batch, others: waiting - batch.length };
  });
}

// A record as the push sends it (03 §6.3): its document, with the number its outbox row keeps.
function envelope({ row, document }: Waiting): Envelope {
  return {
    id: document.id,
    type: document.type,
    schema_version: document.schema_version,
    device_seq: row.device_seq,
    client_time: document.client_time,
    created_by: document.created_by,
    payload: document.payload as Envelope["payload"],
  };
}

// Applies the answers, in the batch's order, all in one transaction: a tab closed halfway leaves every
// row as it was, never one both archived and still waiting. Sent again, the server answers each as
// before (duplicate), so nothing is lost. False when the server stopped at a retry.
async function applyAnswers(
  db: ShopDatabase,
  batch: readonly Waiting[],
  answers: readonly PushedAnswer[],
  sentAt: string,
): Promise<boolean> {
  const byId = new Map(answers.map((answer) => [answer.id, answer]));
  return db.transaction(
    "rw",
    [db.outbox, db.sent_archive, db.pending_effects],
    async () => {
      for (const { row, document } of batch) {
        const answer = byId.get(row.id);
        // The server answers up to its first retry and none after it (SYNC-4): this one and the rest
        // stay waiting, in their order, for the next push.
        if (answer === undefined || answer.status === "retry") {
          if (answer !== undefined)
            await db.outbox.update(row.id, {
              attempts: row.attempts + 1,
              last_error: "retry",
            });
          return false;
        }
        const outcome =
          answer.status === "duplicate" ? answer.first : answer.status;
        if (outcome === "accepted") {
          // Empty when its save changed nothing a laptop keeps a copy of (PushedDocument.posted_seq):
          // still accepted, never a fault, or this one and every record after it would stay stuck.
          const postedSeq = answer.posted_seq;
          await db.outbox.delete(row.id);
          // Kept 30 days, in case a server restore needs it sent again (03 §6.7); clearing it after that is
          // OPS-11's, so for now nothing does.
          await db.sent_archive.put({
            ...document,
            device_seq: row.device_seq,
            sent_at: sentAt,
            posted_seq: postedSeq,
          });
          const effects = db.pending_effects
            .where("document_id")
            .equals(row.id);
          // With a number, the pull drops them once its cursor passes it (SYNC-7). With none, no pull
          // will ever bring a change of it: nothing to wait for, so they go now.
          if (postedSeq === null) await effects.delete();
          else await effects.modify({ posted_seq: postedSeq });
        } else if (outcome === "invalid") {
          // Set aside for someone to look at, with the server's reason (SYNC-11 shows it); the server
          // has raised a flag about it, and the rest of the batch goes on.
          await db.outbox.update(row.id, {
            status: "needs_attention",
            last_error: answer.code,
          });
          // The server saved nothing of it, so no pull will ever bring a change of it: its stock or
          // balance change must not go on being counted on this laptop.
          await db.pending_effects.where("document_id").equals(row.id).delete();
        } else {
          throw new Error(`Duplicate ${row.id} with no first answer.`);
        }
      }
      return true;
    },
  );
}
