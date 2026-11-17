// before-update.test.ts — a tap of Sasisha sends the waiting records first, then lets the update go,
// whatever the send's end: sent, failed, no network, or too slow (SYNC-13, 03 §6.8).
//
// The send is the real sync against the fake server (src/test/fake-server.ts), so the records are seen to
// leave; the slow server is played by a sync that never ends.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { saveDevice } from "@/features/devices/this-device";
import { giveCsrfToken } from "@/test/csrf";
import { DAWA_LAPTOP } from "@/test/devices";
import { answer, sent } from "@/test/fake-server";
import { ASHA } from "@/test/shop-lists";

import { saveDocument } from "../outbox";
import { shopDatabase } from "../this-shop";
import { pushFailed } from "./backoff";
import { SEND_LIMIT, sendBeforeUpdate } from "./before-update";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

const SHOP = DAWA_LAPTOP.shop.id;
const PULL = "/api/sync/v1/pull/";
const PUSH = "/api/sync/v1/push/";

const pushes = () =>
  sent.filter((request) => new URL(request.url).pathname === PUSH);

/** A filled laptop of the Dawa side, with Asha's clock-in waiting in its outbox. */
async function laptopWithAClockIn(): Promise<string> {
  saveDevice(DAWA_LAPTOP);
  giveCsrfToken();
  const db = shopDatabase(SHOP);
  await db.meta.bulkPut([
    { key: "pull_cursor", value: 130 },
    { key: "last_device_seq", value: 57 },
  ]);
  const saved = await saveDocument(db, {
    type: "clock",
    schema_version: 1,
    created_by: ASHA.id,
    payload: { kind: "in", last_server_time: "2026-11-13T04:58:00Z" },
  });
  return saved.id;
}

beforeEach(() => {
  answer("GET", PULL, {
    status: 200,
    body: {
      changes: [],
      cursor: 130,
      has_more: false,
      server_time: "2026-11-13T05:00:00Z",
      min_app_version: 1,
    },
  });
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe("sendBeforeUpdate", () => {
  it("sends the waiting clock-in, even while the push waits after a failure", async () => {
    const id = await laptopWithAClockIn();
    // An earlier push failed, so the next one would wait 30 s (backoff.ts): the tap doesn't.
    await pushFailed(shopDatabase(SHOP), Date.now());
    answer("POST", PUSH, {
      status: 200,
      body: { answers: [{ id, status: "accepted", posted_seq: 131 }] },
    });

    await sendBeforeUpdate();

    expect(pushes()).toHaveLength(1);
    const body = (await pushes()[0]!.clone().json()) as {
      documents: { id: string }[];
    };
    expect(body.documents.map((document) => document.id)).toEqual([id]);
    // Accepted: it left the outbox, so the new version has nothing of the old one's left to send.
    expect(await shopDatabase(SHOP).outbox.count()).toBe(0);
  });

  it("asks nothing on a laptop that isn't registered", async () => {
    const sync = vi.fn();

    await sendBeforeUpdate(sync);

    expect(sync).not.toHaveBeenCalled();
  });

  it("asks nothing with no network, and lets the update go", async () => {
    saveDevice(DAWA_LAPTOP);
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    const sync = vi.fn();

    await sendBeforeUpdate(sync);

    expect(sync).not.toHaveBeenCalled();
  });

  it("lets the update go when the send fails, and keeps the record for the new version", async () => {
    await laptopWithAClockIn();
    // The server's trouble: a 500 on the push, so the record stays waiting (push.ts).
    answer("POST", PUSH, { status: 500, body: {} });
    vi.spyOn(console, "error").mockImplementation(() => {});

    await expect(sendBeforeUpdate()).resolves.toBeUndefined();

    expect(await shopDatabase(SHOP).outbox.count()).toBe(1);
  });

  it("lets the update go after SEND_LIMIT when the server doesn't answer", async () => {
    vi.useFakeTimers();
    saveDevice(DAWA_LAPTOP);
    // A sync that never ends: a server that took the call and never answered.
    const sync = vi.fn(() => new Promise<void>(() => {}));
    let done = false;
    void sendBeforeUpdate(sync).then(() => {
      done = true;
    });

    await vi.advanceTimersByTimeAsync(SEND_LIMIT - 1);
    expect(done).toBe(false);
    await vi.advanceTimersByTimeAsync(1);
    expect(done).toBe(true);
    expect(sync).toHaveBeenCalledWith(SHOP, { sendNow: true });
  });
});
