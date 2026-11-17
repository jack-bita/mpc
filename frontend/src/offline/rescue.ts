// rescue.ts — carrying a dying laptop's unsent records to another laptop of the same shop, in a file
// (SYNC-12, 03 §6.7). It owns the file's shape, the export that writes it and the import that reads it.
//
// The last resort: the Dawa laptop's screen is cracked or its battery is dying, and three clock-ins wait in
// its outbox with no internet to send them. Someone saves them to a file (a USB stick, or a phone), and a
// manager loads the file on the Vyakula laptop, whose push sends them.
//
// Each record keeps its id, the one the Dawa laptop gave it (SYNC-4). That is what makes the rescue safe:
// if the Dawa laptop comes back to life and sends them too, the server finds the id already saved and
// answers `duplicate`, so nothing is saved twice. The same file loaded twice adds each record once, too.
//
// Each record takes the importing laptop's next number. The number is a laptop's own line (device_seq): the
// Vyakula laptop's push sends in its own order, and the Dawa laptop's numbers would break it. So the import
// can't use saveDocument(), which makes a new id, and writes its rows itself, in one transaction, as the
// save does: either the whole file lands, or none of it.
//
// Each record also keeps where it was made: the Dawa laptop and its number there, and the import adds who
// loaded the file (carried_from, db.ts). The push sends it, and the server checks the record's time against
// the Dawa laptop's record before it, not against the Vyakula laptop's last one, which would look like a
// clock moved back (SYNC-12's review); and it names the person who loaded it, who must hold device.manage.
// A record carried twice, Dawa to Vyakula to a third laptop, keeps Dawa as where it was made.
//
// Loaded, a record is in the Vyakula laptop's own documents drawer, as if made there: its "today" list
// (SYNC-11) shows a rescued clock-in of today with the rest, by its maker and its time on the Dawa laptop's
// clock. That is what the shop needs to see: who came in today, whichever laptop sends it.
//
// Only the `waiting` records go in the file. The set-aside ones reached the server already, as refused,
// and sending them again changes nothing (Jack's plan; parking lot 23 decides what to do with them). No
// pending effects either: a clock-in has none. The sale and payment cards, whose records change stock and
// balances, add theirs to the file's next format.
import type { CarriedFrom, DocumentRow, ShopDatabase } from "./db";
import {
  checkDraft,
  HIGHEST_DEVICE_SEQ,
  NeverFilled,
  BrokenDraft,
} from "./outbox";
import { tellRecordSaved } from "./sync/asks";
import { LAST_DEVICE_SEQ, readLastDeviceSeq } from "./sync/meta";
import { waitingInOrder } from "./waiting";

/** The file's own name for itself, so a file of something else is refused at once. */
export const RESCUE_KIND = "mpc.unsent";
/** The file's format. A later format, which this app can't read, is refused, not half read. */
export const RESCUE_FORMAT = 1;

/** Where a record was first made: the laptop and its number there. */
export interface MadeOn {
  device: string;
  device_seq: number;
}

/** One record as the file carries it: the document, its number on the laptop that saved the file, which
 * keeps the file's order, and where it was first made. */
export type RescuedDocument = Omit<DocumentRow, "carried_from"> & {
  device_seq: number;
  made_on: MadeOn;
};

/** What the file holds. */
export interface RescueFile {
  kind: typeof RESCUE_KIND;
  format: typeof RESCUE_FORMAT;
  /** The shop the records belong to: only a laptop of that shop may load them. */
  shop_id: string;
  /** When the file was made, on the dying laptop's clock: for the person choosing between two files. */
  made_at: string;
  documents: RescuedDocument[];
}

/** Why a file was refused: not one of ours (or a later format), another shop's, or a record in it the
 * push can't send, as a file edited by hand may hold. */
export type RescueProblem = "not_rescue_file" | "wrong_shop" | "broken_record";

export class RescueRefused extends Error {
  constructor(readonly problem: RescueProblem) {
    super(`The rescue file was refused: ${problem}.`);
    this.name = "RescueRefused";
  }
}

/**
 * The records waiting on this laptop, as a rescue file, in their number order. Read in one transaction, so
 * a push that sends one meanwhile can't leave its row in the file and its document out.
 */
export async function exportWaiting(
  db: ShopDatabase,
  shopId: string,
  deviceId: string,
): Promise<RescueFile> {
  const documents = await db.transaction(
    "r",
    [db.outbox, db.documents],
    async () => {
      const rows = await waitingInOrder(db).toArray();
      const found = await db.documents.bulkGet(rows.map((row) => row.id));
      return rows.map((row, i) => {
        const document = found[i];
        // Written in one transaction with its row (saveDocument), so never missing.
        if (document === undefined)
          throw new Error(`Outbox row ${row.id} has no document.`);
        // Made here: this laptop and its number. Carried here already: where it was first made, kept.
        const { carried_from, ...rest } = document;
        const made_on: MadeOn = carried_from
          ? { device: carried_from.device, device_seq: carried_from.device_seq }
          : { device: deviceId, device_seq: row.device_seq };
        return { ...rest, device_seq: row.device_seq, made_on };
      });
    },
  );
  return {
    kind: RESCUE_KIND,
    format: RESCUE_FORMAT,
    shop_id: shopId,
    made_at: new Date().toISOString(),
    documents,
  };
}

// Reads the file's text into its shape, checking every part the import trusts: a file can hold anything.
function readFile(text: string, shopId: string): RescueFile {
  let file: unknown;
  try {
    file = JSON.parse(text);
  } catch {
    throw new RescueRefused("not_rescue_file");
  }
  if (
    typeof file !== "object" ||
    file === null ||
    !("kind" in file) ||
    file.kind !== RESCUE_KIND ||
    !("format" in file) ||
    file.format !== RESCUE_FORMAT ||
    !("documents" in file) ||
    !Array.isArray(file.documents)
  )
    throw new RescueRefused("not_rescue_file");
  // Another shop's records: refused whole, before any is read. The server would refuse each one too
  // (`invalid`), but a laptop must not hold another shop's people at all (rule 1).
  if (!("shop_id" in file) || file.shop_id !== shopId)
    throw new RescueRefused("wrong_shop");
  for (const document of file.documents as RescuedDocument[])
    checkRecord(document);
  return file as RescueFile;
}

// A UUID of version 7, as the server's `uuid7_only` takes for a record's id (ADR-0007): the version digit is
// the 13th, and the variant digit, 8 to b, the 17th. Every id this app makes is one (lib/ids.ts); a file
// edited by hand may carry a random one, which the server refuses with the whole push.
const UUID7 =
  /^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

// Any UUID, as the server's check of a laptop's id takes one: laptops' ids are the server's own.
const ANY_UUID =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

// A time as the server's ZonedDateTimeField takes one: an ISO 8601 date and time, ending in its zone, a capital
// `Z` or an offset like +03:00. A day alone, a time with no zone, or a small `z`, is refused there with the
// whole push (ATT-1, SYNC-12's second review). Its parts are kept, so the day and time can be checked too.
const ZONED_TIME =
  /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})$/;

// True for a time the server reads as one: the shape above, and a day and time that exist. JavaScript's own
// reading moves 30 February on to 2 March without a word; the server refuses it.
function isZonedTime(text: string): boolean {
  const parts = ZONED_TIME.exec(text);
  if (parts === null) return false;
  const [year, month, day, hour, minute, second] = parts
    .slice(1)
    .map((part) => Number(part ?? "0"));
  const date = new Date(Date.UTC(year!, month! - 1, day!));
  return (
    date.getUTCFullYear() === year &&
    date.getUTCMonth() === month! - 1 &&
    date.getUTCDate() === day &&
    hour! <= 23 &&
    minute! <= 59 &&
    second! <= 59
  );
}

// A type as the server's text field takes one: it trims the spaces at both ends, so a type of spaces alone is
// empty there, and it refuses the null character, which some databases can't hold.
function isTypeText(type: string): boolean {
  return type.trim().length > 0 && !type.includes("\0");
}

// One record, checked as the push's server checks its envelope (PushedEnvelope,
// apps/sync/api/serializers.py), so a broken one is refused here, at the manager's hands. Let through, it would
// be saved in the outbox, and the server would refuse every push from this laptop with it, for good: every
// clock-in made here after it would stop reaching the server (SYNC-12's review). Each part's kind is checked
// first, as a file's JSON may hold a list or a number where text belongs.
function checkRecord(document: RescuedDocument): void {
  if (
    typeof document !== "object" ||
    document === null ||
    typeof document.type !== "string" ||
    !isTypeText(document.type) ||
    typeof document.created_by !== "string" ||
    typeof document.id !== "string" ||
    !UUID7.test(document.id) ||
    typeof document.client_time !== "string" ||
    !isZonedTime(document.client_time) ||
    !Number.isInteger(document.device_seq) ||
    document.device_seq < 1 ||
    document.device_seq > HIGHEST_DEVICE_SEQ ||
    !madeOnIsWhole(document.made_on)
  )
    throw new RescueRefused("broken_record");
  // The rest as a save checks a screen's draft: the type's length, the shape's version, the maker's id, and
  // a payload that is a plain object.
  try {
    checkDraft(document);
  } catch (error) {
    if (error instanceof BrokenDraft) throw new RescueRefused("broken_record");
    throw error;
  }
}

// Where it was made, as the server's CarriedEnvelope takes it: a laptop's id and a laptop number.
function madeOnIsWhole(madeOn: unknown): boolean {
  if (typeof madeOn !== "object" || madeOn === null) return false;
  const { device, device_seq } = madeOn as Partial<MadeOn>;
  return (
    typeof device === "string" &&
    ANY_UUID.test(device) &&
    Number.isInteger(device_seq) &&
    (device_seq as number) >= 1 &&
    (device_seq as number) <= HIGHEST_DEVICE_SEQ
  );
}

/** What an import did: how many records it added to this laptop's outbox, and how many it found here
 * already (made here, or loaded from this file before). */
export interface ImportResult {
  added: number;
  alreadyHere: number;
}

/**
 * Loads a rescue file's records into this laptop's outbox, each with its own id, this laptop's next number,
 * and where it was made, with `loadedBy`, the staff member loading it; in one transaction, then tells the
 * sync, as a save does. `deviceId` is this laptop's: a record made here goes as this laptop's own.
 */
export async function importWaiting(
  db: ShopDatabase,
  shopId: string,
  deviceId: string,
  text: string,
  loadedBy: string,
): Promise<ImportResult> {
  const file = readFile(text, shopId);
  // In the order they were made on the dying laptop: the push sends them in that order from here too.
  const inOrder = [...file.documents].sort(
    (a, b) => a.device_seq - b.device_seq,
  );
  const result = await db.transaction(
    "rw",
    [db.meta, db.documents, db.outbox, db.sent_archive],
    async () => {
      // Inside the transaction, as in saveDocument: a save in another tab meanwhile takes its turn, and
      // never the same number.
      const before = await readLastDeviceSeq(db);
      if (before === null) throw new NeverFilled();
      let last = before;
      let added = 0;
      let alreadyHere = 0;
      for (const rescued of inOrder) {
        // Only the document's own fields, by name: the saving laptop's number stays behind, and anything
        // else a file may carry never reaches the database. Where it was made goes with it, for the push.
        const document: DocumentRow = {
          id: rescued.id,
          type: rescued.type,
          schema_version: rescued.schema_version,
          client_time: rescued.client_time,
          created_by: rescued.created_by,
          payload: rescued.payload,
        };
        // Made on this very laptop: a laptop whose browser data was wiped keeps its key, so it is the same
        // laptop, loading the file it saved itself. Its records go as its own, as they would have: the server
        // refuses a record "carried" from the laptop that sends it (SYNC-12's second review).
        if (rescued.made_on.device !== deviceId) {
          const carried_from: CarriedFrom = {
            device: rescued.made_on.device,
            device_seq: rescued.made_on.device_seq,
            loaded_by: loadedBy,
          };
          document.carried_from = carried_from;
        }
        // Here already: in documents (made here, or loaded before), or sent from here and archived. Added
        // again it would break the outbox's one row per id, and a second number would be a gap the
        // server flags.
        const known =
          (await db.documents.get(document.id)) ??
          (await db.sent_archive.get(document.id));
        if (known !== undefined) {
          alreadyHere += 1;
          continue;
        }
        const device_seq = last + 1;
        if (device_seq > HIGHEST_DEVICE_SEQ)
          throw new BrokenDraft("device_seq");
        await db.documents.add(document);
        await db.outbox.add({
          id: document.id,
          type: document.type,
          device_seq,
          status: "waiting",
          attempts: 0,
          last_error: null,
        });
        last = device_seq;
        added += 1;
      }
      if (added > 0) await db.meta.put({ key: LAST_DEVICE_SEQ, value: last });
      return { added, alreadyHere };
    },
  );
  // Only once the transaction is in, as after a save: the push finds them there.
  if (result.added > 0) tellRecordSaved();
  return result;
}
