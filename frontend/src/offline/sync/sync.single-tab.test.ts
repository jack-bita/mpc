// sync.single-tab.test.ts — two tabs never sync the same shop at once (SYNC-9, 03 §6.5): a tab waits
// while another holds the shop's lock, from its push to its last pull, and goes once it is handed on,
// however the other tab's sync ended. Each shop has a lock of its own, and a browser without Web Locks
// syncs as before. The other tab is played by the test, through a stand-in lock (src/test/locks.ts).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiRefusal } from "@/api/refusal";
import { DAWA_LAPTOP } from "@/test/devices";
import { giveCsrfToken } from "@/test/csrf";
import { answer, refusal, sent } from "@/test/fake-server";
import {
  installFakeLocks,
  removeFakeLocks,
  type FakeLocks,
} from "@/test/locks";
import { ASHA } from "@/test/shop-lists";

import { saveDocument } from "../outbox";
import { shopDatabase } from "../this-shop";
import { CURSOR, LAST_DEVICE_SEQ } from "./meta";
import { syncLockName } from "./lock";
import { syncShop } from "./sync";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

const SHOP = DAWA_LAPTOP.shop.id;
const OTHER_SHOP = "019a5e00-0000-7000-8000-0000000000a2";
const PUSH = "/api/sync/v1/push/";
const PULL = "/api/sync/v1/pull/";

const PAGE = {
  changes: [],
  cursor: 130,
  has_more: false,
  server_time: "2026-11-12T08:00:00Z",
  min_app_version: null,
};

let locks: FakeLocks;

beforeEach(() => {
  // A working laptop has its CSRF token, from the device check's answer: the push needs it (sync.ts).
  giveCsrfToken();
  locks = installFakeLocks();
  answer("POST", PUSH, { status: 200, body: { answers: [] } });
  answer("GET", PULL, { status: 200, body: PAGE });
});

afterEach(() => {
  removeFakeLocks();
});

const paths = () => sent.map((request) => new URL(request.url).pathname);

/** A moment for anything that was going to start: a sync that waits shows nothing sent after it. */
const aMoment = () => new Promise((resolve) => setTimeout(resolve, 20));

async function filledLaptop(): Promise<void> {
  await shopDatabase(SHOP).meta.bulkPut([
    { key: CURSOR, value: 130 },
    { key: LAST_DEVICE_SEQ, value: 57 },
  ]);
}

describe("one sync at a time across tabs", () => {
  it("sends nothing while another tab syncs the shop, and goes once it ends", async () => {
    // The Dawa laptop has the counter open in two tabs. Asha clocks in in this one while the other syncs.
    await filledLaptop();
    const other = locks.holdInAnotherTab(syncLockName(SHOP));
    await other.granted;
    const made = await saveDocument(shopDatabase(SHOP), {
      type: "clock",
      schema_version: 1,
      created_by: ASHA.id,
      payload: { kind: "in", last_server_time: "2026-11-12T07:58:00Z" },
    });

    const ours = syncShop(SHOP);
    await aMoment();
    expect(sent).toHaveLength(0);

    other.release();
    await ours;
    expect(paths()).toEqual([PUSH, PULL]);
    const body = (await sent[0]!.json()) as { documents: { id: string }[] };
    expect(body.documents.map((document) => document.id)).toEqual([made.id]);
  });

  it("holds the lock from its push to its last pull", async () => {
    // The other tab asks while this one is still pulling: it gets the lock only once the pull is in.
    await filledLaptop();
    let release = (): void => {};
    const held = new Promise<void>((resolve) => {
      release = resolve;
    });
    let pulled = false;
    answer("GET", PULL, async () => {
      await held;
      pulled = true;
      return Response.json(PAGE);
    });

    const ours = syncShop(SHOP);
    await vi.waitFor(() => expect(paths()).toEqual([PUSH, PULL]));
    const other = locks.holdInAnotherTab(syncLockName(SHOP));
    let otherGot = false;
    void other.granted.then(() => {
      otherGot = true;
    });
    await aMoment();
    expect(otherGot).toBe(false);

    release();
    await ours;
    await other.granted;
    expect(pulled).toBe(true);
    other.release();
  });

  it("hands the lock on when its sync fails, so the other tab's goes on", async () => {
    // A fresh laptop meets the server down at its bootstrap; the other tab still gets its turn.
    answer("GET", "/api/sync/v1/bootstrap/", refusal(500, "server_error"));
    const ours = syncShop(SHOP);
    const other = locks.holdInAnotherTab(syncLockName(SHOP));

    await expect(ours).rejects.toBeInstanceOf(ApiRefusal);
    await other.granted;
    other.release();
  });

  it("never waits for another shop's sync", async () => {
    // The practice shop syncing in another tab holds its own lock, not this shop's.
    await filledLaptop();
    const other = locks.holdInAnotherTab(syncLockName(OTHER_SHOP));
    await other.granted;

    await syncShop(SHOP);

    expect(paths()).toEqual([PUSH, PULL]);
    other.release();
  });

  it("syncs as before in a browser without Web Locks", async () => {
    removeFakeLocks();
    await filledLaptop();

    await syncShop(SHOP);

    expect(paths()).toEqual([PUSH, PULL]);
  });
});
