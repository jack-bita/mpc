// attachments.send.test.ts — the photos waiting on the laptop go up once their records are in (CTRL-6, 03 §5.13):
// each to CTRL-3's route, oldest record first, one at a time; kept, it leaves the laptop; not found yet, it waits;
// refused for the file itself, it is set aside and the others go on; with no answer or a server in trouble, the round
// stops; each failed send waits longer before the next; and a sync sends them last, after the pull.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiRefusal } from "@/api/refusal";
import type { components } from "@/api/schema";
import { saveDevice, savedBlocked } from "@/features/devices/this-device";
import { giveCsrfToken } from "@/test/csrf";
import { DAWA_LAPTOP } from "@/test/devices";
import { answer, refusal, sent } from "@/test/fake-server";
import { madeUpJpeg } from "@/test/photos";
import { ASHA } from "@/test/shop-lists";

import { labelPhoto, type LabelledPhoto } from "../attachments";
import type { ShopDatabase } from "../db";
import { saveDocument, type SavedDocument } from "../outbox";
import { shopDatabase } from "../this-shop";
import {
  FIRST_WAIT_MS,
  LONGEST_WAIT_MS,
  MOST_PHOTOS,
  sendAttachments,
} from "./attachments";
import { CURSOR, LAST_DEVICE_SEQ } from "./meta";
import { pagePlace } from "./page-place";
import { push } from "./push";
import { syncShop } from "./sync";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

type PushBody = components["schemas"]["PushBatchRequest"];

const SHOP = DAWA_LAPTOP.shop.id;
const PUSH = "/api/sync/v1/push/";
const PULL = "/api/sync/v1/pull/";
const photoRoute = (id: string) => `/api/sync/v1/attachments/${id}/`;

let db: ShopDatabase;
beforeEach(async () => {
  // A working laptop, filled at change 130, its last record #57, with its CSRF token: the PUT is a change.
  db = shopDatabase(SHOP);
  await db.meta.bulkPut([
    { key: CURSOR, value: 130 },
    { key: LAST_DEVICE_SEQ, value: 57 },
  ]);
  giveCsrfToken();
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

/** Asha's clock-in with its photo, saved together, as ATT-3's screen will save them. */
async function clockInWith(
  photo?: LabelledPhoto,
): Promise<{ record: SavedDocument; photo: LabelledPhoto }> {
  const labelled = photo ?? (await labelPhoto(madeUpJpeg(), "clock_photo"));
  const record = await saveDocument(
    db,
    {
      type: "clock",
      schema_version: 1,
      created_by: ASHA.id,
      payload: { kind: "in", photo: labelled.label },
    },
    [],
    [labelled],
  );
  return { record, photo: labelled };
}

/** `count` clock-ins, each with its photo, #58 onwards. */
async function clockInsWithPhotos(count: number): Promise<LabelledPhoto[]> {
  const photos: LabelledPhoto[] = [];
  for (let i = 0; i < count; i++) photos.push((await clockInWith()).photo);
  return photos;
}

/** Two clock-ins, each with its photo, #58 and #59. */
async function twoClockInsWithPhotos(): Promise<
  [LabelledPhoto, LabelledPhoto]
> {
  return [(await clockInWith()).photo, (await clockInWith()).photo];
}

/** The push, with the server accepting every record (whose handler writes each photo's row, ATT-3). */
async function recordsAccepted(): Promise<void> {
  let next = 131;
  answer("POST", PUSH, async (request) => {
    const body = (await request.json()) as PushBody;
    return Response.json({
      answers: body.documents.map((document) => ({
        id: document.id,
        status: "accepted",
        posted_seq: next++,
      })),
    });
  });
  await push(db, pagePlace);
}

/** The server keeps each of these photos (204). */
function keeps(...photos: LabelledPhoto[]): void {
  for (const photo of photos)
    answer("PUT", photoRoute(photo.label.id), { status: 204 });
}

/** The photos sent, in order, by their ids. */
const photosSent = () =>
  sent
    .filter((request) => request.method === "PUT")
    .map((request) => new URL(request.url).pathname.split("/").at(-2));

const bytesOf = (bytes: ArrayBuffer) => Array.from(new Uint8Array(bytes));

describe("sending the photos", () => {
  it("sends a photo once its record is in, and takes it off the laptop", async () => {
    const { photo } = await clockInWith();
    await recordsAccepted();
    keeps(photo);

    await sendAttachments(db, pagePlace);

    const request = sent.find((one) => one.method === "PUT");
    expect(request?.url).toBe(`http://shop.test${photoRoute(photo.label.id)}`);
    // The file's bytes alone, with its type and the CSRF token, as the push's change carries it (CTRL-3).
    expect(request?.headers.get("Content-Type")).toBe("image/jpeg");
    expect(request?.headers.get("X-CSRFToken")).toBe("token-from-django");
    expect(bytesOf(await request!.arrayBuffer())).toEqual(bytesOf(photo.bytes));
    expect(await db.attachment_files.count()).toBe(0);
  });

  it("keeps a photo whose record hasn't gone yet, and asks nothing", async () => {
    // Before its record, the server holds no row for it: sent, it could only answer "not found".
    await clockInWith();

    await sendAttachments(db, pagePlace);

    expect(photosSent()).toEqual([]);
    expect(await db.attachment_files.toArray()).toMatchObject([
      { state: "waiting", tries: 0 },
    ]);
  });

  it("keeps a photo whose record was set aside, as the server holds no row for it", async () => {
    const { record } = await clockInWith();
    answer("POST", PUSH, {
      status: 200,
      body: {
        answers: [
          { id: record.id, status: "invalid", code: "document.type_unknown" },
        ],
      },
    });
    await push(db, pagePlace);

    await sendAttachments(db, pagePlace);

    expect(photosSent()).toEqual([]);
    expect(await db.attachment_files.toArray()).toMatchObject([
      { state: "waiting", tries: 0 },
    ]);
  });

  it("sends the photos in their records' order, one at a time", async () => {
    // Labelled the other way round from their records, so their ids run against their numbers: the photos go as
    // their records went, never in id order.
    const third = await labelPhoto(madeUpJpeg(), "clock_photo");
    const second = await labelPhoto(madeUpJpeg(), "clock_photo");
    const first = await labelPhoto(madeUpJpeg(), "clock_photo");
    for (const photo of [first, second, third]) await clockInWith(photo);
    await recordsAccepted();
    let atOnce = 0;
    let mostAtOnce = 0;
    for (const photo of [first, second, third])
      answer("PUT", photoRoute(photo.label.id), async () => {
        atOnce += 1;
        mostAtOnce = Math.max(mostAtOnce, atOnce);
        await new Promise((resolve) => setTimeout(resolve, 5));
        atOnce -= 1;
        return new Response(null, { status: 204 });
      });

    await sendAttachments(db, pagePlace);

    expect(photosSent()).toEqual([first, second, third].map((p) => p.label.id));
    expect(mostAtOnce).toBe(1);
  });

  it("leaves a photo the server can't find yet waiting, and sends the others", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-11-17T05:00:00Z"));
    const [lost, next] = await twoClockInsWithPhotos();
    await recordsAccepted();
    answer(
      "PUT",
      photoRoute(lost.label.id),
      refusal(404, "attachment.not_found"),
    );
    keeps(next);

    await sendAttachments(db, pagePlace);

    expect(photosSent()).toEqual([lost.label.id, next.label.id]);
    expect(await db.attachment_files.get(lost.label.id)).toMatchObject({
      state: "waiting",
      tries: 1,
      last_error: "attachment.not_found",
      wait_until: Date.now() + FIRST_WAIT_MS,
    });
    expect(await db.attachment_files.get(next.label.id)).toBeUndefined();
  });

  it.each([
    "attachment.too_big",
    "attachment.not_an_image",
    "attachment.file_differs",
  ])("sets aside a photo refused as %s, and sends the others", async (code) => {
    const [refused, next] = await twoClockInsWithPhotos();
    await recordsAccepted();
    answer("PUT", photoRoute(refused.label.id), refusal(400, code));
    keeps(next);

    await sendAttachments(db, pagePlace);

    expect(await db.attachment_files.toArray()).toEqual([
      expect.objectContaining({
        id: refused.label.id,
        state: "set_aside",
        tries: 1,
        last_error: code,
        wait_until: null,
      }),
    ]);
    // The same file would get the same answer: a later sync never sends it again.
    await sendAttachments(db, pagePlace);
    expect(photosSent()).toEqual([refused.label.id, next.label.id]);
  });

  it.each([
    { when: "the network drops", status: null, code: null },
    { when: "the server has a problem", status: 500, code: "server_error" },
    {
      when: "the photo went with no length",
      status: 411,
      code: "attachment.length_required",
    },
    { when: "the server has no such route", status: 404, code: "not_found" },
  ])(
    "stops the round when $when, and keeps every photo",
    async ({ status, code }) => {
      vi.useFakeTimers({ toFake: ["Date"] });
      vi.setSystemTime(new Date("2026-11-17T05:00:00Z"));
      const [first, second] = await twoClockInsWithPhotos();
      await recordsAccepted();
      answer(
        "PUT",
        photoRoute(first.label.id),
        status === null || code === null
          ? () => {
              // fetch's own way of saying no answer came (NoConnection, make-client.ts).
              throw new TypeError("Failed to fetch");
            }
          : refusal(status, code),
      );
      keeps(second);

      await sendAttachments(db, pagePlace);

      expect(photosSent()).toEqual([first.label.id]);
      expect(await db.attachment_files.get(first.label.id)).toMatchObject({
        state: "waiting",
        tries: 1,
        last_error: code,
        wait_until: Date.now() + FIRST_WAIT_MS,
      });
      expect(await db.attachment_files.get(second.label.id)).toMatchObject({
        state: "waiting",
        tries: 0,
      });
    },
  );

  it("waits longer after each failed send, at most an hour", async () => {
    // A sync every 30 s would otherwise send the same 150 KB 2,880 times a day.
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-11-17T05:00:00Z"));
    const { photo } = await clockInWith();
    await recordsAccepted();
    answer("PUT", photoRoute(photo.label.id), refusal(500, "server_error"));
    const waits: number[] = [];

    for (let i = 0; i < 8; i++) {
      const wentAt = Date.now();
      await sendAttachments(db, pagePlace);
      const until = (await db.attachment_files.get(photo.label.id))?.wait_until;
      if (until === null || until === undefined) throw new Error("no wait");
      waits.push((until - wentAt) / 60_000);
      // A moment before its wait ends, a sync sends nothing.
      vi.setSystemTime(until - 1);
      const before = photosSent().length;
      await sendAttachments(db, pagePlace);
      expect(photosSent()).toHaveLength(before);
      vi.setSystemTime(until);
    }

    expect(waits).toEqual([1, 2, 4, 8, 16, 32, 60, 60]);
    expect(LONGEST_WAIT_MS).toBe(60 * 60_000);
  });

  it("sends a photo whose wait the laptop's clock put far back", async () => {
    // The clock was put back a day after a failed send: no real wait is over an hour, so the photo goes.
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-11-17T05:00:00Z"));
    const { photo } = await clockInWith();
    await recordsAccepted();
    await db.attachment_files.update(photo.label.id, {
      tries: 1,
      wait_until: Date.now() + 24 * 60 * 60_000,
    });
    keeps(photo);

    await sendAttachments(db, pagePlace);

    expect(await db.attachment_files.count()).toBe(0);
  });

  it("locks the app when the laptop is blocked, and keeps the photo as it was", async () => {
    // An unblock brings back the same key, so the photo can still go (03 §5.9, step 4).
    saveDevice(DAWA_LAPTOP);
    const { photo } = await clockInWith();
    await recordsAccepted();
    answer("PUT", photoRoute(photo.label.id), refusal(401, "device.blocked"));

    await expect(sendAttachments(db, pagePlace)).rejects.toBeInstanceOf(
      ApiRefusal,
    );

    expect(savedBlocked()).toBe(true);
    expect(await db.attachment_files.toArray()).toMatchObject([
      { state: "waiting", tries: 0, last_error: null, wait_until: null },
    ]);
  });

  it("sends at most 10 photos a sync, and the rest at the next", async () => {
    const photos = await clockInsWithPhotos(MOST_PHOTOS + 2);
    await recordsAccepted();
    keeps(...photos);

    await sendAttachments(db, pagePlace);
    expect(photosSent()).toHaveLength(MOST_PHOTOS);
    expect(await db.attachment_files.count()).toBe(2);

    await sendAttachments(db, pagePlace);
    expect(await db.attachment_files.count()).toBe(0);
  });
});

describe("a sync", () => {
  beforeEach(() => {
    answer("GET", PULL, {
      status: 200,
      body: {
        changes: [],
        cursor: 131,
        has_more: false,
        server_time: "2026-11-17T05:00:00Z",
        min_app_version: 1,
      },
    });
  });

  const paths = () => sent.map((request) => new URL(request.url).pathname);

  it("sends the record, then the server's changes come down, then the photo goes", async () => {
    // Done when: a record saved with a photo while offline keeps both; once the record is accepted, the photo goes
    // up and leaves the laptop. Last, so a week of photos never holds up a suspension coming down (X2).
    const { record, photo } = await clockInWith();
    answer("POST", PUSH, {
      status: 200,
      body: {
        answers: [{ id: record.id, status: "accepted", posted_seq: 131 }],
      },
    });
    keeps(photo);

    await syncShop(SHOP);

    expect(paths()).toEqual([PUSH, PULL, photoRoute(photo.label.id)]);
    expect(await db.attachment_files.count()).toBe(0);
  });

  it("sends no photo when its push failed", async () => {
    // The line or the server is in trouble, and a photo is far bigger than a record: it waits for a push that works.
    const { record, photo } = await clockInWith();
    answer("POST", PUSH, {
      status: 200,
      body: {
        answers: [{ id: record.id, status: "accepted", posted_seq: 131 }],
      },
    });
    await push(db, pagePlace);
    keeps(photo);
    answer("POST", PUSH, refusal(502, "server_error"));

    await expect(syncShop(SHOP)).rejects.toBeInstanceOf(ApiRefusal);

    expect(paths().at(-1)).toBe(PULL);
    expect(await db.attachment_files.count()).toBe(1);
  });
});
