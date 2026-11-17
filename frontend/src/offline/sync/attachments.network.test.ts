// attachments.network.test.ts — Wi-Fi first, where the browser can tell (CTRL-6, 03 §5.13): on mobile data, or with a
// data saver on, the photos wait, and their records still go; where the browser says nothing, as Chrome on a Windows
// laptop, Firefox or Safari, the photos go (Jack, 17 Nov 2026).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { components } from "@/api/schema";
import { giveCsrfToken } from "@/test/csrf";
import { DAWA_LAPTOP } from "@/test/devices";
import { answer, sent } from "@/test/fake-server";
import { madeUpJpeg } from "@/test/photos";
import { ASHA } from "@/test/shop-lists";

import { labelPhoto, type LabelledPhoto } from "../attachments";
import type { ShopDatabase } from "../db";
import { saveDocument } from "../outbox";
import { shopDatabase } from "../this-shop";
import { onCostlyLine, sendAttachments } from "./attachments";
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
  db = shopDatabase(SHOP);
  await db.meta.bulkPut([
    { key: CURSOR, value: 130 },
    { key: LAST_DEVICE_SEQ, value: 57 },
  ]);
  giveCsrfToken();
  // The server accepts every record, and keeps every photo it is sent.
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

afterEach(() => {
  // The browser's own navigator, with no connection of the test's.
  Reflect.deleteProperty(navigator, "connection");
});

/** What the browser says of the line, as Chrome does on a phone; left out, the browser says nothing, as Firefox. */
function onLine(connection: { type?: string; saveData?: boolean }): void {
  Object.defineProperty(navigator, "connection", {
    value: connection,
    configurable: true,
  });
}

/** Asha's clock-in with its photo, saved together, and the server's answer for the photo: kept. */
async function clockInWithPhoto(): Promise<LabelledPhoto> {
  const photo = await labelPhoto(madeUpJpeg(), "clock_photo");
  await saveDocument(
    db,
    {
      type: "clock",
      schema_version: 1,
      created_by: ASHA.id,
      payload: { kind: "in", photo: photo.label },
    },
    [],
    [photo],
  );
  answer("PUT", photoRoute(photo.label.id), { status: 204 });
  return photo;
}

const photosSent = () => sent.filter((request) => request.method === "PUT");

describe("Wi-Fi first", () => {
  it.each([
    ["mobile data", { type: "cellular" }],
    ["mobile data with no data saver", { type: "cellular", saveData: false }],
    ["Wi-Fi with a data saver on", { type: "wifi", saveData: true }],
    ["no type, with a data saver on", { saveData: true }],
  ])("keeps the photos on %s", async (_, connection) => {
    await clockInWithPhoto();
    await push(db, pagePlace);
    onLine(connection);

    await sendAttachments(db, pagePlace);

    expect(photosSent()).toEqual([]);
    // Waiting for Wi-Fi is no failed send: the photo waits as it was, with no wait of its own to sit out after.
    expect(await db.attachment_files.toArray()).toMatchObject([
      { state: "waiting", tries: 0, wait_until: null },
    ]);
  });

  it.each([
    ["Wi-Fi", { type: "wifi", saveData: false }],
    ["a cable", { type: "ethernet" }],
    ["a line the browser can't name, as Chrome on a Windows laptop", {}],
  ])("sends the photos on %s", async (_, connection) => {
    await clockInWithPhoto();
    await push(db, pagePlace);
    onLine(connection);

    await sendAttachments(db, pagePlace);

    expect(photosSent()).toHaveLength(1);
    expect(await db.attachment_files.count()).toBe(0);
  });

  it("sends the photos where the browser says nothing of its line, as Firefox and Safari", async () => {
    // No navigator.connection at all: taken at its word, as a laptop that can't tell (Jack, 17 Nov 2026).
    expect("connection" in navigator).toBe(false);
    expect(onCostlyLine()).toBe(false);
    await clockInWithPhoto();
    await push(db, pagePlace);

    await sendAttachments(db, pagePlace);

    expect(photosSent()).toHaveLength(1);
  });

  it("sends the record on mobile data, and its photo once the device is on Wi-Fi", async () => {
    // Done when: where the browser says the laptop is on mobile data, the photos wait for Wi-Fi. The record itself
    // is small, and the office needs it: it never waits.
    await clockInWithPhoto();
    onLine({ type: "cellular" });

    await syncShop(SHOP);

    expect(await db.outbox.count()).toBe(0);
    expect(photosSent()).toEqual([]);
    expect(await db.attachment_files.count()).toBe(1);

    onLine({ type: "wifi" });
    await syncShop(SHOP);

    expect(photosSent()).toHaveLength(1);
    expect(await db.attachment_files.count()).toBe(0);
  });
});
