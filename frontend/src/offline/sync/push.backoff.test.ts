// push.backoff.test.ts — after a push the server told to try later, or one that failed, the next push
// waits (SYNC-8): 30 s, then twice as long each time, never more than 5 minutes. A push that settles
// starts the wait again from 30 s. Meanwhile the pull still runs, and each shop waits on its own. The wait
// is kept in the shop's database, so every tab and a reload wait alike (SYNC-9); Tuma sasa doesn't wait.
import { beforeEach, describe, expect, it, vi } from "vitest";

import { NoConnection } from "@/api/refusal";
import type { components } from "@/api/schema";
import { DAWA_LAPTOP } from "@/test/devices";
import { answer, sent } from "@/test/fake-server";
import { ASHA } from "@/test/shop-lists";

import { openShopDatabase } from "../db";
import { saveDocument } from "../outbox";
import { closeShopDatabases, shopDatabase } from "../this-shop";
import { mayPush } from "./backoff";
import { CURSOR, LAST_DEVICE_SEQ } from "./meta";
import { syncShop } from "./sync";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

type PushBody = components["schemas"]["PushBatchRequest"];

const SHOP = DAWA_LAPTOP.shop.id;
const PUSH = "/api/sync/v1/push/";
const PULL = "/api/sync/v1/pull/";

// 08:00 on the shop's morning, by the laptop's clock: the waits are counted from here.
const START = new Date("2026-11-12T08:00:00Z").getTime();
function secondsLater(seconds: number): void {
  vi.setSystemTime(START + seconds * 1000);
}

/** The shop's laptop, filled, with Asha's clock-in waiting in its outbox. */
async function filledLaptop(shopId = SHOP): Promise<void> {
  const db = shopDatabase(shopId);
  await db.meta.bulkPut([
    { key: CURSOR, value: 130 },
    { key: LAST_DEVICE_SEQ, value: 57 },
  ]);
  await clockIn(shopId);
}

async function clockIn(shopId = SHOP): Promise<void> {
  await saveDocument(shopDatabase(shopId), {
    type: "clock",
    schema_version: 1,
    created_by: ASHA.id,
    payload: { kind: "in", last_server_time: "2026-11-12T07:58:00Z" },
  });
}

/** The server has trouble saving: it answers the first record with retry. */
function serverSaysTryLater(): void {
  answer("POST", PUSH, async (request) => {
    const [first] = ((await request.json()) as PushBody).documents;
    return Response.json({
      answers: [
        {
          id: first!.id,
          status: "retry",
          first: null,
          posted_seq: null,
          flags: [],
          code: "",
          fields: {},
        },
      ],
    });
  });
}

/** The server saves every record it is sent. */
function serverAccepts(): void {
  let next = 201;
  answer("POST", PUSH, async (request) =>
    Response.json({
      answers: ((await request.json()) as PushBody).documents.map(
        (document) => ({
          id: document.id,
          status: "accepted",
          first: null,
          posted_seq: next++,
          flags: [],
          code: "",
          fields: {},
        }),
      ),
    }),
  );
}

const count = (path: string) =>
  sent.filter((request) => new URL(request.url).pathname === path).length;

beforeEach(() => {
  // Only the clock is fake: Dexie and the fake server keep their own timers.
  vi.useFakeTimers({ toFake: ["Date"] });
  secondsLater(0);
  answer("GET", PULL, {
    status: 200,
    body: {
      changes: [],
      cursor: 130,
      has_more: false,
      server_time: "2026-11-12T08:00:00Z",
      min_app_version: null,
    },
  });
});

describe("the wait before the next push", () => {
  it("is 30 s after a retry, and the pull still runs meanwhile", async () => {
    await filledLaptop();
    serverSaysTryLater();

    await syncShop(SHOP);
    expect(count(PUSH)).toBe(1);

    secondsLater(29);
    await syncShop(SHOP);
    expect(count(PUSH)).toBe(1);
    // The office's changes still come down while the push waits.
    expect(count(PULL)).toBe(2);

    secondsLater(30);
    await syncShop(SHOP);
    expect(count(PUSH)).toBe(2);
  });

  it("doubles after each retry, and never passes 5 minutes", async () => {
    await filledLaptop();
    serverSaysTryLater();

    let at = 0;
    let pushes = 0;
    for (const wait of [30, 60, 120, 240, 300, 300]) {
      // The wait before this one is over (none before the first): the push goes, and is told to wait.
      secondsLater(at);
      await syncShop(SHOP);
      expect(count(PUSH)).toBe(++pushes);
      // A second before this wait ends: still waiting.
      secondsLater(at + wait - 1);
      await syncShop(SHOP);
      expect(count(PUSH)).toBe(pushes);
      at += wait;
    }
  });

  it("starts again from 30 s after a push that settles", async () => {
    await filledLaptop();
    serverSaysTryLater();
    await syncShop(SHOP); // waits 30 s
    secondsLater(30);
    await syncShop(SHOP); // waits 60 s

    secondsLater(90);
    serverAccepts();
    await syncShop(SHOP);
    expect(await shopDatabase(SHOP).outbox.count()).toBe(0);

    // The next trouble waits 30 s, not 120 s.
    await clockIn();
    secondsLater(91);
    serverSaysTryLater();
    await syncShop(SHOP);
    const pushed = count(PUSH);
    secondsLater(120);
    await syncShop(SHOP);
    expect(count(PUSH)).toBe(pushed);
    secondsLater(121);
    await syncShop(SHOP);
    expect(count(PUSH)).toBe(pushed + 1);
  });

  it("follows a push that failed, as a retry does", async () => {
    // No network: the sync fails, and the next push waits all the same.
    await filledLaptop();
    answer("POST", PUSH, () => {
      throw new TypeError("Failed to fetch");
    });
    await expect(syncShop(SHOP)).rejects.toBeInstanceOf(NoConnection);

    serverAccepts();
    secondsLater(29);
    await syncShop(SHOP);
    expect(count(PUSH)).toBe(1);

    secondsLater(30);
    await syncShop(SHOP);
    expect(count(PUSH)).toBe(2);
  });

  it("never lasts longer than 5 minutes, even when the laptop's clock is put back", async () => {
    // A shop laptop's clock is often wrong (03 §6.6). Put back an hour in the middle of a 30 s wait,
    // the wait would otherwise run on for an hour and a half.
    await filledLaptop();
    serverSaysTryLater();
    await syncShop(SHOP);

    secondsLater(-3600);
    await syncShop(SHOP);

    expect(count(PUSH)).toBe(2);
  });

  it("doesn't hold back Tuma sasa, and its failure makes the next wait longer", async () => {
    // Asha presses Tuma sasa 5 s into a 30 s wait: it goes (Jack, 12 Nov 2026). The server still has
    // trouble, so the next wait is the doubled one, 60 s from her press.
    await filledLaptop();
    serverSaysTryLater();
    await syncShop(SHOP);

    secondsLater(5);
    await syncShop(SHOP, { sendNow: true });
    expect(count(PUSH)).toBe(2);

    secondsLater(64);
    await syncShop(SHOP);
    expect(count(PUSH)).toBe(2);
    secondsLater(65);
    await syncShop(SHOP);
    expect(count(PUSH)).toBe(3);
  });

  it("makes the sync after the running one push, when Tuma sasa is pressed meanwhile", async () => {
    // A 30 s sync is pulling, its push held back by the wait, when Asha presses Tuma sasa: the sync
    // that runs next pushes, even though a plain ask came first.
    await filledLaptop();
    serverSaysTryLater();
    await syncShop(SHOP);
    secondsLater(5);
    let release = (): void => {};
    const held = new Promise<void>((resolve) => {
      release = resolve;
    });
    let pulls = 0;
    answer("GET", PULL, async () => {
      pulls += 1;
      // The first pull after this answer was set: the running sync's.
      if (pulls === 1) await held;
      return Response.json({
        changes: [],
        cursor: 130,
        has_more: false,
        server_time: "2026-11-12T08:00:05Z",
        min_app_version: null,
      });
    });

    const running = syncShop(SHOP);
    await vi.waitFor(() => expect(pulls).toBe(1));
    const plain = syncShop(SHOP);
    const pressed = syncShop(SHOP, { sendNow: true });
    expect(pressed).toBe(plain);
    release();
    await Promise.all([running, pressed]);

    expect(count(PUSH)).toBe(2);
  });

  it("is kept in the shop's database, so another tab and a reload wait too", async () => {
    // This tab was told to wait. Another tab, with its own connection to the same database, must not
    // push the moment after: the server in trouble would get the push twice as often.
    await filledLaptop();
    serverSaysTryLater();
    await syncShop(SHOP);

    const otherTab = openShopDatabase(SHOP);
    secondsLater(29);
    expect(await mayPush(otherTab)).toBe(false);
    secondsLater(30);
    expect(await mayPush(otherTab)).toBe(true);
    otherTab.close();

    // A reload: every connection of this tab gone, nothing left in its memory. Its first sync, 10 s
    // into the next wait, still waits.
    await syncShop(SHOP);
    expect(count(PUSH)).toBe(2);
    closeShopDatabases();
    secondsLater(40);
    await syncShop(SHOP);
    expect(count(PUSH)).toBe(2);
  });

  it("is each shop's own", async () => {
    // The laptop's other shop (the practice shop, say) has no trouble: it pushes at once.
    const other = "019a5e00-0000-7000-8000-0000000000a2";
    await filledLaptop();
    await filledLaptop(other);
    serverSaysTryLater();
    await syncShop(SHOP);

    secondsLater(5);
    await syncShop(other);

    expect(count(PUSH)).toBe(2);
  });
});
