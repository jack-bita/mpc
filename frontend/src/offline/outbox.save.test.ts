// outbox.save.test.ts — saving a document on the laptop (SYNC-8, 03 §6.2): the document, its number
// and its outbox row, written in one transaction or not at all, its number one past the last.
import Dexie from "dexie";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DAWA_LAPTOP } from "@/test/devices";
import { ASHA } from "@/test/shop-lists";

import { openShopDatabase, type ShopDatabase } from "./db";
import { NeverFilled, saveDocument, type Draft } from "./outbox";
import { LAST_DEVICE_SEQ, readLastDeviceSeq } from "./sync/meta";

let db: ShopDatabase;
afterEach(async () => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  db.close();
  await Dexie.delete(db.name);
});

/** The Dawa laptop, already filled: its bootstrap said its last record was #57. */
async function filledLaptop(last = 57): Promise<ShopDatabase> {
  db = openShopDatabase(DAWA_LAPTOP.shop.id);
  await db.meta.put({ key: LAST_DEVICE_SEQ, value: last });
  return db;
}

/** Asha clocks in: the document ATT-1's server takes (SYNC-11 builds the screen that makes it). */
const CLOCK_IN: Draft = {
  type: "clock",
  schema_version: 1,
  created_by: ASHA.id,
  payload: { kind: "in", last_server_time: "2026-11-12T04:58:00Z" },
};

describe("saving a document", () => {
  it("writes the document, its number and its outbox row", async () => {
    await filledLaptop();
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-11-12T05:00:30Z"));

    const saved = await saveDocument(db, CLOCK_IN);

    expect(saved.device_seq).toBe(58);
    // The laptop's clock as it was made, with its zone, as the push sends it (ATT-1).
    expect(await db.documents.get(saved.id)).toEqual({
      id: saved.id,
      ...CLOCK_IN,
      client_time: "2026-11-12T05:00:30.000Z",
    });
    expect(await db.outbox.get(saved.id)).toEqual({
      id: saved.id,
      type: "clock",
      device_seq: 58,
      status: "waiting",
      attempts: 0,
      last_error: null,
    });
    expect(await readLastDeviceSeq(db)).toBe(58);
  });

  it("numbers each one past the last, in the order they are saved", async () => {
    await filledLaptop();

    const first = await saveDocument(db, CLOCK_IN);
    const second = await saveDocument(db, CLOCK_IN);
    const third = await saveDocument(db, CLOCK_IN);

    expect([first, second, third].map((saved) => saved.device_seq)).toEqual([
      58, 59, 60,
    ]);
    // A new id each time: three taps are three documents, never one sent three times.
    expect(new Set([first.id, second.id, third.id]).size).toBe(3);
  });

  it("gives two saves at the same moment two numbers", async () => {
    // Asha and Baraka tap at once, in two tabs: each save reads the number inside its own transaction,
    // so the second waits for the first, and never reads the same #57.
    await filledLaptop();

    const both = await Promise.all([
      saveDocument(db, CLOCK_IN),
      saveDocument(db, CLOCK_IN),
    ]);

    expect(both.map((saved) => saved.device_seq).sort()).toEqual([58, 59]);
    expect(await readLastDeviceSeq(db)).toBe(59);
  });

  it("saves nothing at all when one of its writes fails", async () => {
    // The last write fails, as a full disk would make it: the document, the outbox row and the number
    // go back with it. Kept, the document would never be sent; the number, skipped for good.
    await filledLaptop();
    vi.spyOn(db.pending_effects, "bulkAdd").mockRejectedValueOnce(
      new Error("disk full"),
    );

    await expect(saveDocument(db, CLOCK_IN, [{}])).rejects.toThrow("disk full");

    expect(await db.documents.count()).toBe(0);
    expect(await db.outbox.count()).toBe(0);
    expect(await db.pending_effects.count()).toBe(0);
    expect(await readLastDeviceSeq(db)).toBe(57);
  });

  it("writes its pending effects with it, not yet posted", async () => {
    // A sale's stock change, say: the screens count it until the server's own numbers include it.
    await filledLaptop();

    const saved = await saveDocument(db, CLOCK_IN, [{}, {}]);

    const effects = await db.pending_effects.toArray();
    expect(effects).toHaveLength(2);
    for (const effect of effects) {
      expect(effect).toEqual({
        id: expect.any(String),
        document_id: saved.id,
        posted_seq: null,
      });
    }
  });

  it("refuses on a laptop never filled, and writes nothing", async () => {
    // No bootstrap yet, so no number from the server: counting from 1 could take a number it already
    // used before a wipe (SYNC-5's note).
    db = openShopDatabase(DAWA_LAPTOP.shop.id);

    await expect(saveDocument(db, CLOCK_IN)).rejects.toBeInstanceOf(
      NeverFilled,
    );

    expect(await db.documents.count()).toBe(0);
    expect(await db.outbox.count()).toBe(0);
    expect(await readLastDeviceSeq(db)).toBeNull();
  });
});
