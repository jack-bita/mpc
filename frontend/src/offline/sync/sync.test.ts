// sync.test.ts — one sync of the laptop's shop (SYNC-7): the bootstrap once, then the push (SYNC-8), then
// pulls; a second check while one runs joins it; a failed one leaves the next free to run.
import { beforeEach, describe, expect, it, vi } from "vitest";

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
    await shopDatabase(SHOP).meta.put({ key: "pull_cursor", value: 130 });
    answer("GET", PULL, emptyPage(130));

    await syncShop(SHOP);

    expect(paths()).toEqual([PUSH, PULL]);
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

  it("joins the sync already running instead of starting a second", async () => {
    answer("GET", BOOTSTRAP_ROUTE, { status: 200, body: BOOTSTRAP });
    answer("GET", PULL, emptyPage(120));

    const first = syncShop(SHOP);
    const second = syncShop(SHOP);
    await Promise.all([first, second]);

    expect(second).toBe(first);
    expect(paths()).toEqual([BOOTSTRAP_ROUTE, PUSH, PULL]);
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

  it("leaves the next sync free to run after one fails", async () => {
    answer("GET", BOOTSTRAP_ROUTE, refusal(500, "server_error"));
    await expect(syncShop(SHOP)).rejects.toThrow();

    answer("GET", BOOTSTRAP_ROUTE, { status: 200, body: BOOTSTRAP });
    answer("GET", PULL, emptyPage(120));
    await syncShop(SHOP);

    expect(await readCursor(shopDatabase(SHOP))).toBe(120);
  });
});
