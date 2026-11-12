// sync.test.ts — one sync of the laptop's shop (SYNC-7): the bootstrap once, then the push (SYNC-8), then
// pulls; one asked for while another runs runs once more after it, and asks beyond that join it (SYNC-9);
// a failed one leaves the next free to run.
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiRefusal } from "@/api/refusal";
import { saveDevice, savedBlocked } from "@/features/devices/this-device";

import { DAWA_LAPTOP } from "@/test/devices";
import { answer, refusal, sent } from "@/test/fake-server";
import { ASHA, BOOTSTRAP } from "@/test/shop-lists";

import { saveDocument } from "../outbox";
import { shopDatabase } from "../this-shop";
import { readCursor } from "./meta";
import { syncShop } from "./sync";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

const SHOP = DAWA_LAPTOP.shop.id;
const BOOTSTRAP_ROUTE = "/api/sync/v1/bootstrap/";
const PULL = "/api/sync/v1/pull/";
const PUSH = "/api/sync/v1/push/";

// Every sync pushes first: with nothing waiting, the push is the laptop's report alone (push.loop.test.ts).
beforeEach(() => {
  answer("POST", PUSH, { status: 200, body: { answers: [] } });
});

const emptyPage = (cursor: number) => ({
  status: 200,
  body: {
    changes: [],
    cursor,
    has_more: false,
    server_time: "2026-11-11T09:00:00Z",
    min_app_version: null,
  },
});

const paths = () => sent.map((request) => new URL(request.url).pathname);

/** A filled laptop: its cursor and its last number, as a bootstrap leaves them. */
async function filledLaptop(): Promise<void> {
  await shopDatabase(SHOP).meta.bulkPut([
    { key: "pull_cursor", value: 130 },
    { key: "last_device_seq", value: 57 },
  ]);
}

/** Asha's clock-in, saved on the laptop. */
const clockIn = () =>
  saveDocument(shopDatabase(SHOP), {
    type: "clock",
    schema_version: 1,
    created_by: ASHA.id,
    payload: { kind: "in", last_server_time: "2026-11-12T04:58:00Z" },
  });

/**
 * The pull's first answer, held until the test lets it go: a sync stopped halfway, its push gone, while
 * the test asks again. `pulls` counts the pulls asked for, so a test can wait for the first to arrive.
 */
function holdTheFirstPull(): { release: () => void; pulls: () => number } {
  let release = nothing;
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });
  let pulls = 0;
  answer("GET", PULL, async () => {
    pulls += 1;
    if (pulls === 1) await held;
    return Response.json(emptyPage(130).body);
  });
  return { release: () => release(), pulls: () => pulls };
}

function nothing(): void {}

describe("a sync", () => {
  it("bootstraps a fresh laptop, pushes, then pulls from its cursor", async () => {
    answer("GET", BOOTSTRAP_ROUTE, { status: 200, body: BOOTSTRAP });
    answer("GET", PULL, emptyPage(120));

    await syncShop(SHOP);

    expect(paths()).toEqual([BOOTSTRAP_ROUTE, PUSH, PULL]);
    expect(new URL(sent[2]!.url).searchParams.get("cursor")).toBe("120");
    expect(await readCursor(shopDatabase(SHOP))).toBe(120);
  });

  it("only pushes and pulls on a laptop already filled", async () => {
    await shopDatabase(SHOP).meta.bulkPut([
      { key: "pull_cursor", value: 130 },
      { key: "last_device_seq", value: 57 },
    ]);
    answer("GET", PULL, emptyPage(130));

    await syncShop(SHOP);

    expect(paths()).toEqual([PUSH, PULL]);
  });

  it("fills again a laptop filled before its number was kept", async () => {
    // A laptop SYNC-7 filled has a cursor but no number of its own: one more bootstrap gives it one.
    await shopDatabase(SHOP).meta.put({ key: "pull_cursor", value: 110 });
    answer("GET", BOOTSTRAP_ROUTE, { status: 200, body: BOOTSTRAP });
    answer("GET", PULL, emptyPage(120));

    await syncShop(SHOP);

    expect(paths()).toEqual([BOOTSTRAP_ROUTE, PUSH, PULL]);
  });

  it("sends what waits before it pulls", async () => {
    // Asha's clock-in leaves first: the pull that follows then brings what the server made of it.
    const db = shopDatabase(SHOP);
    await db.meta.bulkPut([
      { key: "pull_cursor", value: 130 },
      { key: "last_device_seq", value: 57 },
    ]);
    const made = await saveDocument(db, {
      type: "clock",
      schema_version: 1,
      created_by: ASHA.id,
      payload: { kind: "in", last_server_time: "2026-11-12T04:58:00Z" },
    });
    answer("GET", PULL, emptyPage(130));

    await syncShop(SHOP);

    expect(paths()).toEqual([PUSH, PULL]);
    const body = (await sent[0]!.json()) as { documents: { id: string }[] };
    expect(body.documents.map((document) => document.id)).toEqual([made.id]);
  });

  it("still pulls when the push is told to try later", async () => {
    // A retry is the server's trouble saving one record: the office's changes can still come down.
    const db = shopDatabase(SHOP);
    await db.meta.bulkPut([
      { key: "pull_cursor", value: 130 },
      { key: "last_device_seq", value: 57 },
    ]);
    const made = await saveDocument(db, {
      type: "clock",
      schema_version: 1,
      created_by: ASHA.id,
      payload: { kind: "in", last_server_time: "2026-11-12T04:58:00Z" },
    });
    answer("POST", PUSH, {
      status: 200,
      body: {
        answers: [
          {
            id: made.id,
            status: "retry",
            first: null,
            posted_seq: null,
            flags: [],
            code: "",
            fields: {},
          },
        ],
      },
    });
    answer("GET", PULL, emptyPage(130));

    await syncShop(SHOP);

    expect(paths()).toEqual([PUSH, PULL]);
    expect(await db.outbox.count()).toBe(1);
  });

  it("runs once more after the running one, and the asks after that join it", async () => {
    await filledLaptop();
    const pull = holdTheFirstPull();

    const first = syncShop(SHOP);
    await vi.waitFor(() => expect(pull.pulls()).toBe(1));
    const second = syncShop(SHOP);
    const third = syncShop(SHOP);
    // Two at most: never two at once, and never a third waiting.
    expect(second).not.toBe(first);
    expect(third).toBe(second);
    expect(paths()).toEqual([PUSH, PULL]);

    pull.release();
    await Promise.all([first, second]);

    expect(paths()).toEqual([PUSH, PULL, PUSH, PULL]);
  });

  it("sends a record saved while a sync pulls, right after it", async () => {
    // The sync had pushed already when Asha clocked in: hers goes at once, not at the next moment.
    await filledLaptop();
    const pull = holdTheFirstPull();
    const first = syncShop(SHOP);
    await vi.waitFor(() => expect(pull.pulls()).toBe(1));

    const made = await clockIn();
    const second = syncShop(SHOP);
    pull.release();
    await Promise.all([first, second]);

    const body = (await sent[2]!.json()) as { documents: { id: string }[] };
    expect(body.documents.map((document) => document.id)).toEqual([made.id]);
  });

  it("runs the one asked after it, even when the running one fails", async () => {
    // The first bootstrap meets the server down; the sync asked meanwhile fills the laptop.
    let release = nothing;
    const held = new Promise<void>((resolve) => {
      release = resolve;
    });
    let bootstraps = 0;
    answer("GET", BOOTSTRAP_ROUTE, async () => {
      bootstraps += 1;
      if (bootstraps > 1) return Response.json(BOOTSTRAP);
      await held;
      return Response.json(refusal(500, "server_error").body, { status: 500 });
    });
    answer("GET", PULL, emptyPage(120));

    const first = syncShop(SHOP);
    await vi.waitFor(() => expect(bootstraps).toBe(1));
    const second = syncShop(SHOP);
    release();

    await expect(first).rejects.toBeInstanceOf(ApiRefusal);
    await second;
    expect(await readCursor(shopDatabase(SHOP))).toBe(120);
  });

  it("never joins another shop's sync", async () => {
    // The laptop was moved to another shop while its old shop's sync still ran.
    const other = "019a5e00-0000-7000-8000-0000000000a2";
    answer("GET", BOOTSTRAP_ROUTE, { status: 200, body: BOOTSTRAP });
    answer("GET", PULL, emptyPage(120));

    const first = syncShop(SHOP);
    const second = syncShop(other);
    await Promise.all([first, second]);

    expect(second).not.toBe(first);
    expect(await readCursor(shopDatabase(other))).toBe(120);
  });

  it("still pulls when the push fails, then throws the push's failure", async () => {
    // The server has trouble with the push route alone: the office's changes, a suspension among them
    // (X2), must still come down. The failure is thrown after, so it is still reported.
    await shopDatabase(SHOP).meta.bulkPut([
      { key: "pull_cursor", value: 130 },
      { key: "last_device_seq", value: 57 },
    ]);
    answer("POST", PUSH, refusal(500, "server_error"));
    answer("GET", PULL, emptyPage(131));

    await expect(syncShop(SHOP)).rejects.toBeInstanceOf(ApiRefusal);

    expect(paths()).toEqual([PUSH, PULL]);
    expect(await readCursor(shopDatabase(SHOP))).toBe(131);
  });

  it("pulls nothing once the push says the laptop is blocked", async () => {
    // A blocked laptop must ask nothing more: the lock is on (answer.ts).
    saveDevice(DAWA_LAPTOP);
    await shopDatabase(SHOP).meta.bulkPut([
      { key: "pull_cursor", value: 130 },
      { key: "last_device_seq", value: 57 },
    ]);
    answer("POST", PUSH, refusal(401, "device.blocked"));
    answer("GET", PULL, emptyPage(131));

    await expect(syncShop(SHOP)).rejects.toBeInstanceOf(ApiRefusal);

    expect(savedBlocked()).toBe(true);
    expect(paths()).toEqual([PUSH]);
  });

  it("leaves the next sync free to run after one fails", async () => {
    answer("GET", BOOTSTRAP_ROUTE, refusal(500, "server_error"));
    await expect(syncShop(SHOP)).rejects.toThrow();

    answer("GET", BOOTSTRAP_ROUTE, { status: 200, body: BOOTSTRAP });
    answer("GET", PULL, emptyPage(120));
    await syncShop(SHOP);

    expect(await readCursor(shopDatabase(SHOP))).toBe(120);
  });
});
