// attachments.save.test.ts — a photo taken on the laptop, labelled and saved with its record (CTRL-6, 03 §5.13):
// its label read from its own bytes, as the server will read them; a photo the server would refuse refused here,
// at the counter; and the record, its number, its outbox row and its photo written in one transaction, or none.
import { createHash } from "node:crypto";

import Dexie from "dexie";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DAWA_LAPTOP } from "@/test/devices";
import { madeUpJpeg, madeUpPng, madeUpWebp } from "@/test/photos";
import { ASHA } from "@/test/shop-lists";

import {
  BrokenPhoto,
  LARGEST_PHOTO,
  labelPhoto,
  type LabelledPhoto,
} from "./attachments";
import { openShopDatabase, type ShopDatabase } from "./db";
import { NeverFilled, saveDocument, type Draft } from "./outbox";
import { LAST_DEVICE_SEQ, readLastDeviceSeq } from "./sync/meta";

// The database a test opened, closed and deleted after it. Only the saving tests open one: the labelling tests need
// none.
let opened: ShopDatabase | undefined;
afterEach(async () => {
  vi.restoreAllMocks();
  if (opened === undefined) return;
  opened.close();
  await Dexie.delete(opened.name);
  opened = undefined;
});

/** The Dawa laptop, never filled: no bootstrap yet. */
function newLaptop(): ShopDatabase {
  opened = openShopDatabase(DAWA_LAPTOP.shop.id);
  return opened;
}

/** The Dawa laptop, already filled: its bootstrap said its last record was #57. */
async function filledLaptop(): Promise<ShopDatabase> {
  const db = newLaptop();
  await db.meta.put({ key: LAST_DEVICE_SEQ, value: 57 });
  return db;
}

/** The bytes of a photo, as one plain list to compare. The pretend database hands its bytes back made by Node's own
 * ArrayBuffer, not the test page's, so `expect.any(ArrayBuffer)` can't tell them: the bytes themselves can. */
function bytesOf(bytes: ArrayBuffer | undefined): number[] {
  return Array.from(new Uint8Array(bytes ?? new ArrayBuffer(0)));
}

/** Asha clocks in with her photo. Where the payload names it is ATT-3's to choose; here, `photo`. */
function clockInWith(photo: LabelledPhoto): Draft {
  return {
    type: "clock",
    schema_version: 1,
    created_by: ASHA.id,
    payload: { kind: "in", photo: photo.label },
  };
}

/** The SHA-256 of a file, worked out by Node's own crypto, not the browser's: the label must match it. */
async function sha256Of(file: Blob): Promise<string> {
  return createHash("sha256")
    .update(new Uint8Array(await file.arrayBuffer()))
    .digest("hex");
}

describe("labelling a photo", () => {
  it("reads a JPEG's label from its bytes", async () => {
    const file = madeUpJpeg(200);

    const photo = await labelPhoto(file, "clock_photo");

    expect(photo.label).toEqual({
      id: expect.stringMatching(/^[0-9a-f-]{36}$/),
      kind: "clock_photo",
      content_type: "image/jpeg",
      size: 200,
      // 64 lower-case hex digits, as the server compares them (CTRL-3).
      sha256: await sha256Of(file),
    });
    expect(bytesOf(photo.bytes)).toEqual(bytesOf(await file.arrayBuffer()));
  });

  it("reads a WebP by its first bytes", async () => {
    const photo = await labelPhoto(madeUpWebp(), "clock_photo");

    expect(photo.label.content_type).toBe("image/webp");
  });

  it("takes the type from the bytes, not from what the file says it is", async () => {
    // A camera that names its JPEG wrongly: the server sniffs the bytes, so the label must say what they say,
    // or the photo would be refused as `file_differs` once its record was in.
    const photo = await labelPhoto(madeUpJpeg(64, "image/png"), "clock_photo");

    expect(photo.label.content_type).toBe("image/jpeg");
  });

  it("gives each photo an id of its own", async () => {
    const first = await labelPhoto(madeUpJpeg(), "clock_photo");
    const second = await labelPhoto(madeUpJpeg(), "clock_photo");

    expect(first.label.id).not.toBe(second.label.id);
  });

  it.each([
    ["a PNG", madeUpPng()],
    ["an empty file", new Blob([], { type: "image/jpeg" })],
  ])(
    "refuses %s, as the server keeps only a JPEG or a WebP",
    async (_, file) => {
      await expect(labelPhoto(file, "clock_photo")).rejects.toEqual(
        new BrokenPhoto("not_an_image"),
      );
    },
  );

  it("keeps a photo of exactly 1 MB, and refuses one byte more", async () => {
    // The server's limit, to the byte (CTRL-3): over it, the photo would wait on the laptop only to be set aside.
    expect(LARGEST_PHOTO).toBe(1_048_576);
    await expect(
      labelPhoto(madeUpJpeg(LARGEST_PHOTO), "clock_photo"),
    ).resolves.toMatchObject({ label: { size: LARGEST_PHOTO } });

    await expect(
      labelPhoto(madeUpJpeg(LARGEST_PHOTO + 1), "clock_photo"),
    ).rejects.toEqual(new BrokenPhoto("too_big"));
  });
});

describe("saving a record with its photo", () => {
  it("writes the photo with its record, waiting to go", async () => {
    const db = await filledLaptop();
    const photo = await labelPhoto(madeUpJpeg(), "clock_photo");

    const saved = await saveDocument(db, clockInWith(photo), [], [photo]);

    expect(await db.documents.get(saved.id)).toMatchObject({
      payload: { kind: "in", photo: photo.label },
    });
    const row = await db.attachment_files.get(photo.label.id);
    expect(row).toEqual({
      ...photo.label,
      document_id: saved.id,
      device_seq: 58,
      bytes: expect.anything(),
      state: "waiting",
      tries: 0,
      last_error: null,
      wait_until: null,
    });
    // The bytes as the camera made them: the same file the label's fingerprint was worked out from.
    expect(bytesOf(row?.bytes)).toEqual(bytesOf(photo.bytes));
  });

  it("writes two photos of one record, each with its own row", async () => {
    // STK-4's delivery may come with two pages of the supplier's paper.
    const db = await filledLaptop();
    const first = await labelPhoto(madeUpJpeg(), "clock_photo");
    const second = await labelPhoto(madeUpWebp(), "clock_photo");
    const draft: Draft = {
      ...clockInWith(first),
      payload: { photos: [first.label, second.label] },
    };

    const saved = await saveDocument(db, draft, [], [first, second]);

    const rows = await db.attachment_files.toArray();
    expect(rows.map((row) => row.document_id)).toEqual([saved.id, saved.id]);
  });

  it("saves nothing at all when the photo's write fails", async () => {
    // A full disk as the photo is written: the record, its number and its outbox row go back with it. Kept,
    // the record would name a photo the laptop never had, and the server would wait for it for good.
    const db = await filledLaptop();
    const photo = await labelPhoto(madeUpJpeg(), "clock_photo");
    vi.spyOn(db.attachment_files, "bulkAdd").mockRejectedValueOnce(
      new Error("disk full"),
    );

    await expect(
      saveDocument(db, clockInWith(photo), [], [photo]),
    ).rejects.toThrow("disk full");

    expect(await db.documents.count()).toBe(0);
    expect(await db.outbox.count()).toBe(0);
    expect(await db.attachment_files.count()).toBe(0);
    expect(await readLastDeviceSeq(db)).toBe(57);
  });

  it("keeps no photo of a record that couldn't be saved", async () => {
    // A laptop never filled can't number a record (SYNC-8): its photo isn't kept either, so no photo waits for
    // a record that never was.
    const db = newLaptop();
    const photo = await labelPhoto(madeUpJpeg(), "clock_photo");

    await expect(
      saveDocument(db, clockInWith(photo), [], [photo]),
    ).rejects.toBeInstanceOf(NeverFilled);

    expect(await db.attachment_files.count()).toBe(0);
  });

  it("refuses a photo its record doesn't name, and saves nothing", async () => {
    // The server writes a photo's row from its record's label (ATT-3): a photo the record forgot would get no
    // row, and wait on the laptop for good. A bug in the screen, so it fails at the counter.
    const db = await filledLaptop();
    const photo = await labelPhoto(madeUpJpeg(), "clock_photo");
    const forgot: Draft = { ...clockInWith(photo), payload: { kind: "in" } };

    await expect(saveDocument(db, forgot, [], [photo])).rejects.toEqual(
      new BrokenPhoto("not_named"),
    );

    expect(await db.documents.count()).toBe(0);
    expect(await db.attachment_files.count()).toBe(0);
  });

  it("saves a record with no photo as before", async () => {
    const db = await filledLaptop();

    await saveDocument(db, {
      type: "clock",
      schema_version: 1,
      created_by: ASHA.id,
      payload: { kind: "in" },
    });

    expect(await db.documents.count()).toBe(1);
    expect(await db.attachment_files.count()).toBe(0);
  });
});
