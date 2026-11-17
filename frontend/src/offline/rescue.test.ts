// rescue.test.ts — carrying a dying laptop's unsent records to another laptop of the same shop (SYNC-12,
// 03 §6.7). Two laptops of the Dawa shop, each with its own database: the Dawa laptop, dying with three
// clock-ins unsent, and the Vyakula laptop, which loads its file. That the server saves each record once,
// whichever laptop sends it first, is the backend's test (test_push.py, a record carried to another laptop).
import Dexie from "dexie";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DAWA_LAPTOP } from "@/test/devices";
import { ASHA } from "@/test/shop-lists";

import { type DocumentRow, openShopDatabase, type ShopDatabase } from "./db";
import {
  type Draft,
  NeverFilled,
  type SavedDocument,
  saveDocument,
} from "./outbox";
import {
  exportWaiting,
  importWaiting,
  RESCUE_FORMAT,
  RESCUE_KIND,
  RescueRefused,
} from "./rescue";
import { listenForAsks } from "./sync/asks";
import { LAST_DEVICE_SEQ, readLastDeviceSeq } from "./sync/meta";
import { waitingInOrder } from "./waiting";

const SHOP = DAWA_LAPTOP.shop.id;
/** The Vyakula laptop's id, for a file it saves itself. */
const VYAKULA_LAPTOP = "019a5e00-0000-7000-8000-0000000000e2";
/** The manager who loads the file on the Vyakula laptop. */
const NEEMA = "019a5e00-0000-7000-8000-0000000000c4";
const OTHER_SHOP = "019a5e00-0000-7000-8000-00000000ffff";

const opened: ShopDatabase[] = [];
afterEach(async () => {
  vi.restoreAllMocks();
  for (const db of opened.splice(0)) {
    db.close();
    await Dexie.delete(db.name);
  }
});

/** A laptop of the Dawa shop, filled by its bootstrap, its last record `last`. Each gets a database of its
 * own: in the shop, two laptops are two browsers. */
async function laptop(name: string, last: number): Promise<ShopDatabase> {
  const db = openShopDatabase(name);
  opened.push(db);
  await db.meta.put({ key: LAST_DEVICE_SEQ, value: last });
  return db;
}

/** Asha's clock-in, `kind` in or out. */
const clock = (kind: "in" | "out"): Draft => ({
  type: "clock",
  schema_version: 1,
  created_by: ASHA.id,
  payload: { kind, last_server_time: "2026-11-12T04:58:00Z" },
});

/** A saved document as its documents row keeps it: without its number, which its outbox row holds. */
function withoutNumber(saved: SavedDocument): DocumentRow {
  const { id, type, schema_version, client_time, created_by, payload } = saved;
  return { id, type, schema_version, client_time, created_by, payload };
}

/** The Dawa laptop with three clock-ins unsent, #58 to #60, and the file it saves. */
async function dyingLaptop() {
  const dawa = await laptop("dawa-test", 57);
  const saved = [
    await saveDocument(dawa, clock("in")),
    await saveDocument(dawa, clock("out")),
    await saveDocument(dawa, clock("in")),
  ];
  const text = JSON.stringify(await exportWaiting(dawa, SHOP, DAWA_LAPTOP.id));
  return { dawa, saved, text };
}

describe("the export", () => {
  it("writes every waiting record, in its order, with its id, its number and where it was made", async () => {
    const { saved, text } = await dyingLaptop();
    const file = JSON.parse(text) as Record<string, unknown>;

    expect(file.kind).toBe(RESCUE_KIND);
    expect(file.format).toBe(RESCUE_FORMAT);
    expect(file.shop_id).toBe(SHOP);
    expect(file.documents).toEqual(
      saved.map((document) => ({
        ...document,
        made_on: { device: DAWA_LAPTOP.id, device_seq: document.device_seq },
      })),
    );
  });

  it("keeps where a record carried here was first made, when it is carried on again", async () => {
    // Vyakula loaded Dawa's file, and is dying too before it sent them: its own file still says Dawa, #58.
    const { saved, text } = await dyingLaptop();
    const vyakula = await laptop("vyakula-test", 140);
    await importWaiting(vyakula, SHOP, VYAKULA_LAPTOP, text, NEEMA);

    const again = await exportWaiting(vyakula, SHOP, VYAKULA_LAPTOP);
    expect(again.documents[0]).toMatchObject({
      id: saved[0]!.id,
      device_seq: 141,
      made_on: { device: DAWA_LAPTOP.id, device_seq: 58 },
    });
    // The loader stays behind: the next laptop names its own.
    expect(again.documents[0]).not.toHaveProperty("carried_from");
  });

  it("leaves out a record the server refused: it reached the server already", async () => {
    const { dawa, saved } = await dyingLaptop();
    await dawa.outbox.update(saved[1]!.id, {
      status: "needs_attention",
      last_error: "document.type_unknown",
    });

    const file = await exportWaiting(dawa, SHOP, DAWA_LAPTOP.id);
    expect(file.documents.map((document) => document.id)).toEqual([
      saved[0]!.id,
      saved[2]!.id,
    ]);
  });
});

describe("the import", () => {
  it("adds each record to the other laptop's outbox, keeping its id and taking that laptop's next number", async () => {
    const { saved, text } = await dyingLaptop();
    const vyakula = await laptop("vyakula-test", 140);

    expect(
      await importWaiting(vyakula, SHOP, VYAKULA_LAPTOP, text, NEEMA),
    ).toEqual({
      added: 3,
      alreadyHere: 0,
    });

    // Its own ids, so the server knows each one if the Dawa laptop sends it too; Vyakula's numbers, 141 on,
    // in the order they were made, so its push sends them in that order.
    const waiting = await waitingInOrder(vyakula).toArray();
    expect(waiting.map((row) => [row.id, row.device_seq])).toEqual([
      [saved[0]!.id, 141],
      [saved[1]!.id, 142],
      [saved[2]!.id, 143],
    ]);
    expect(await readLastDeviceSeq(vyakula)).toBe(143);
    // The documents as made, on the Dawa laptop's clock, the dying laptop's number left behind; and where each
    // was made, with who loaded it, for the push to tell the server (SYNC-12's review).
    expect(await vyakula.documents.get(saved[0]!.id)).toEqual({
      ...withoutNumber(saved[0]!),
      carried_from: {
        device: DAWA_LAPTOP.id,
        device_seq: 58,
        loaded_by: NEEMA,
      },
    });
  });

  it("sends a laptop's own records as its own, when it loads the file it saved itself", async () => {
    // Dawa's browser data was wiped, and its key kept, so it is the same laptop: it loads its own file. The
    // server refuses a record "carried" from the laptop that sends it, so these carry nothing (SYNC-12's
    // second review).
    const { saved, text } = await dyingLaptop();
    const wiped = await laptop("dawa-wiped-test", 60);

    expect(
      await importWaiting(wiped, SHOP, DAWA_LAPTOP.id, text, NEEMA),
    ).toEqual({ added: 3, alreadyHere: 0 });
    const document = await wiped.documents.get(saved[0]!.id);
    expect(document).toEqual(withoutNumber(saved[0]!));
    expect(document).not.toHaveProperty("carried_from");
  });

  it("adds each record once when the same file is loaded twice", async () => {
    const { text } = await dyingLaptop();
    const vyakula = await laptop("vyakula-test", 140);
    await importWaiting(vyakula, SHOP, VYAKULA_LAPTOP, text, NEEMA);

    expect(
      await importWaiting(vyakula, SHOP, VYAKULA_LAPTOP, text, NEEMA),
    ).toEqual({
      added: 0,
      alreadyHere: 3,
    });
    expect(await vyakula.outbox.count()).toBe(3);
    expect(await readLastDeviceSeq(vyakula)).toBe(143);
  });

  it("skips a record this laptop sent already, kept in its archive", async () => {
    const { saved, text } = await dyingLaptop();
    const vyakula = await laptop("vyakula-test", 140);
    await vyakula.sent_archive.add({
      ...withoutNumber(saved[0]!),
      device_seq: 141,
      sent_at: "2026-11-12T06:00:00Z",
      posted_seq: 300,
    });

    expect(
      await importWaiting(vyakula, SHOP, VYAKULA_LAPTOP, text, NEEMA),
    ).toEqual({
      added: 2,
      alreadyHere: 1,
    });
  });

  it("tells the sync once the records are in, as a save does", async () => {
    const { text } = await dyingLaptop();
    const vyakula = await laptop("vyakula-test", 140);
    const heard = vi.fn();
    const stop = listenForAsks(heard);

    await importWaiting(vyakula, SHOP, VYAKULA_LAPTOP, text, NEEMA);
    expect(heard).toHaveBeenCalledWith("saved");
    stop();
  });

  it("refuses another shop's file, and adds nothing", async () => {
    const { text } = await dyingLaptop();
    const vyakula = await laptop("vyakula-test", 140);

    await expect(
      importWaiting(vyakula, OTHER_SHOP, VYAKULA_LAPTOP, text, NEEMA),
    ).rejects.toEqual(new RescueRefused("wrong_shop"));
    expect(await vyakula.outbox.count()).toBe(0);
  });

  it.each([
    ["text that isn't JSON", "a shopping list"],
    ["another kind of file", JSON.stringify({ kind: "photo", documents: [] })],
    [
      "a later format",
      JSON.stringify({
        kind: RESCUE_KIND,
        format: RESCUE_FORMAT + 1,
        shop_id: SHOP,
        documents: [],
      }),
    ],
  ])("refuses %s", async (_, text) => {
    const vyakula = await laptop("vyakula-test", 140);
    await expect(
      importWaiting(vyakula, SHOP, VYAKULA_LAPTOP, text, NEEMA),
    ).rejects.toEqual(new RescueRefused("not_rescue_file"));
  });

  it("refuses the whole file when one record is broken, as a file edited by hand may be", async () => {
    const { text } = await dyingLaptop();
    const file = JSON.parse(text) as { documents: Record<string, unknown>[] };
    file.documents[2]!.id = "not-an-id";
    const vyakula = await laptop("vyakula-test", 140);

    await expect(
      importWaiting(vyakula, SHOP, VYAKULA_LAPTOP, JSON.stringify(file), NEEMA),
    ).rejects.toEqual(new RescueRefused("broken_record"));
    // Not the first two either: the file lands whole or not at all.
    expect(await vyakula.outbox.count()).toBe(0);
  });

  // Each one the server would refuse with the whole push, so the laptop that loaded it could never send again
  // (PushedEnvelope, apps/sync/api/serializers.py; SYNC-12's review).
  it.each<[string, (record: Record<string, unknown>) => void]>([
    [
      "an id of version 4",
      (r) => (r.id = "0b8c5a6e-4f1d-4a2b-9c3d-5e6f7a8b9c0d"),
    ],
    [
      "an id with no version 7 variant",
      (r) => (r.id = "019a5e00-0000-7000-0000-000000000001"),
    ],
    ["a time with no zone", (r) => (r.client_time = "2026-11-13T07:30:00")],
    ["a small z for its zone", (r) => (r.client_time = "2026-11-13T07:30:00z")],
    [
      "a day that doesn't exist",
      (r) => (r.client_time = "2026-02-30T07:30:00Z"),
    ],
    ["a 31 November", (r) => (r.client_time = "2026-11-31T07:30:00Z")],
    ["an hour past 23", (r) => (r.client_time = "2026-11-13T24:30:00Z")],
    ["a type of spaces alone", (r) => (r.type = "   ")],
    ["a type with a null character", (r) => (r.type = "clo\u0000ck")],
    ["a day alone", (r) => (r.client_time = "2026-11-13")],
    ["a type that isn't text", (r) => (r.type = ["clock"])],
    ["no type at all", (r) => (r.type = null)],
    ["a maker that isn't text", (r) => (r.created_by = 42)],
    ["a number below 1", (r) => (r.device_seq = 0)],
    ["a number that isn't whole", (r) => (r.device_seq = 5.5)],
    ["a payload that is a list", (r) => (r.payload = [])],
    ["no laptop it was made on", (r) => delete r.made_on],
    [
      "a laptop that isn't an id",
      (r) => (r.made_on = { device: "Laptop Dawa", device_seq: 58 }),
    ],
    [
      "a number on its laptop below 1",
      (r) => (r.made_on = { device: DAWA_LAPTOP.id, device_seq: 0 }),
    ],
  ])("refuses a record with %s", async (_, breakIt) => {
    const { text } = await dyingLaptop();
    const file = JSON.parse(text) as { documents: Record<string, unknown>[] };
    breakIt(file.documents[1]!);
    const vyakula = await laptop("vyakula-test", 140);

    await expect(
      importWaiting(vyakula, SHOP, VYAKULA_LAPTOP, JSON.stringify(file), NEEMA),
    ).rejects.toEqual(new RescueRefused("broken_record"));
    expect(await vyakula.outbox.count()).toBe(0);
  });

  it("takes 29 February in a leap year", async () => {
    const { text } = await dyingLaptop();
    const file = JSON.parse(text) as { documents: Record<string, unknown>[] };
    file.documents[1]!.client_time = "2028-02-29T07:30:00Z";
    const vyakula = await laptop("vyakula-test", 140);

    expect(
      await importWaiting(
        vyakula,
        SHOP,
        VYAKULA_LAPTOP,
        JSON.stringify(file),
        NEEMA,
      ),
    ).toEqual({ added: 3, alreadyHere: 0 });
  });

  it("takes a time with an offset, as the server does", async () => {
    const { text } = await dyingLaptop();
    const file = JSON.parse(text) as { documents: Record<string, unknown>[] };
    file.documents[1]!.client_time = "2026-11-13T07:30:00.123+03:00";
    const vyakula = await laptop("vyakula-test", 140);

    expect(
      await importWaiting(
        vyakula,
        SHOP,
        VYAKULA_LAPTOP,
        JSON.stringify(file),
        NEEMA,
      ),
    ).toEqual({
      added: 3,
      alreadyHere: 0,
    });
  });

  it("refuses on a laptop never filled, which doesn't know where its count stands", async () => {
    const { text } = await dyingLaptop();
    const fresh = openShopDatabase("fresh-test");
    opened.push(fresh);

    await expect(
      importWaiting(fresh, SHOP, VYAKULA_LAPTOP, text, NEEMA),
    ).rejects.toBeInstanceOf(NeverFilled);
    expect(await fresh.outbox.count()).toBe(0);
  });
});
