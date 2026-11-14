// push.outages.test.ts — the offline periods go with the push (SYNC-14, 03 §6.3): the closed ones, oldest
// first, up to 100 a push; each kept on the laptop until a push gets the server's answer, a retry
// included, as the server keeps them whatever the documents' answers; an open one waits until it closes.
import Dexie from "dexie";
import { afterEach, describe, expect, it, vi } from "vitest";

import { NoConnection } from "@/api/refusal";
import type { components } from "@/api/schema";
import { DAWA_LAPTOP } from "@/test/devices";
import { answer, refusal, sent } from "@/test/fake-server";
import { ASHA } from "@/test/shop-lists";

import { openShopDatabase, type OutageRow, type ShopDatabase } from "../db";
import { saveDocument } from "../outbox";
import { CURSOR, LAST_DEVICE_SEQ } from "./meta";
import { MOST_OUTAGES } from "./outages";
import { pagePlace } from "./page-place";
import { push } from "./push";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

type PushBody = components["schemas"]["PushBatchRequest"];

const PUSH = "/api/sync/v1/push/";

let db: ShopDatabase;
afterEach(async () => {
  db.close();
  await Dexie.delete(db.name);
});

/** The Dawa laptop, filled at change 120, whose last record was #57. */
async function filledLaptop(): Promise<void> {
  db = openShopDatabase(DAWA_LAPTOP.shop.id);
  await db.meta.bulkPut([
    { key: CURSOR, value: 120 },
    { key: LAST_DEVICE_SEQ, value: 57 },
  ]);
}

/** A period the moments closed: the `n`th of the day, from 10:0n for a minute. Its id is a UUIDv7 that
 * grows with `n`, as ids made later do. */
function closed(n: number): OutageRow {
  const start = Date.parse("2026-11-14T10:00:00Z") + n * 60_000;
  return {
    id: `019a8000-0000-7000-8000-${n.toString(16).padStart(12, "0")}`,
    started_at: new Date(start).toISOString(),
    ended_at: new Date(start + 60_000).toISOString(),
    seen_at: new Date(start + 60_000).toISOString(),
  };
}

/** The period the laptop is in now, not closed yet. */
const STILL_OPEN: OutageRow = {
  id: "019a8000-0000-7000-8000-0000000fffff",
  started_at: "2026-11-14T11:00:00.000Z",
  ended_at: null,
  seen_at: "2026-11-14T11:00:30.000Z",
};

/** A period as the push sends it: no seen_at, the laptop's own. */
const asSent = ({ id, started_at, ended_at }: OutageRow) => ({
  id,
  started_at,
  ended_at,
});

/** What each push carried, in order. */
async function bodies(): Promise<PushBody[]> {
  return Promise.all(
    sent
      .filter((request) => new URL(request.url).pathname === PUSH)
      .map(async (request) => (await request.clone().json()) as PushBody),
  );
}

const nothingToAnswer = { status: 200, body: { answers: [] } };

describe("the push's offline periods", () => {
  it("go with the push, the closed ones oldest first, and are forgotten once the server answers", async () => {
    // Two short cuts this morning, and the one the laptop is in now.
    await filledLaptop();
    await db.outages.bulkAdd([closed(2), STILL_OPEN, closed(1)]);
    answer("POST", PUSH, nothingToAnswer);

    await push(db, pagePlace);

    const [body] = await bodies();
    expect(body?.outages).toEqual([asSent(closed(1)), asSent(closed(2))]);
    expect(await db.outages.toArray()).toEqual([STILL_OPEN]);
  });

  it("stay on the laptop when the push gets no answer, and go again with the next", async () => {
    await filledLaptop();
    await db.outages.bulkAdd([closed(1), closed(2)]);
    answer("POST", PUSH, () => {
      throw new TypeError("Failed to fetch");
    });

    await expect(push(db, pagePlace)).rejects.toBeInstanceOf(NoConnection);
    expect(await db.outages.count()).toBe(2);

    answer("POST", PUSH, nothingToAnswer);
    await push(db, pagePlace);

    const [, again] = await bodies();
    expect(again?.outages).toEqual([asSent(closed(1)), asSent(closed(2))]);
    expect(await db.outages.count()).toBe(0);
  });

  it("stay on the laptop when the server refuses the push", async () => {
    // A 503 while the server restarts: it saved nothing of this push.
    await filledLaptop();
    await db.outages.bulkAdd([closed(1)]);
    answer("POST", PUSH, refusal(503, "server_error"));

    await expect(push(db, pagePlace)).rejects.toThrow();

    expect(await db.outages.count()).toBe(1);
  });

  it("are forgotten after an answer that says retry, as the server kept them all the same", async () => {
    // Asha's clock-in meets trouble on the server (retry), but the periods were recorded after it
    // (apps/sync/push.py): sent again they would be kept once, but there is no need.
    await filledLaptop();
    const clockIn = await saveDocument(db, {
      type: "clock",
      schema_version: 1,
      created_by: ASHA.id,
      payload: { kind: "in", last_server_time: "2026-11-14T04:58:00Z" },
    });
    await db.outages.bulkAdd([closed(1)]);
    answer("POST", PUSH, {
      status: 200,
      body: {
        answers: [
          {
            id: clockIn.id,
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

    expect(await push(db, pagePlace)).toBe("retry");

    expect(await db.outages.count()).toBe(0);
    expect(await db.outbox.count()).toBe(1);
  });

  it("go 100 a push, and the pushes go on while they fill one", async () => {
    // A week of a flickering line: 150 short cuts, and no record waiting.
    await filledLaptop();
    const many = Array.from({ length: 150 }, (_, i) => closed(i + 1));
    await db.outages.bulkAdd(many);
    answer("POST", PUSH, nothingToAnswer);

    expect(await push(db, pagePlace)).toBe("sent");

    const [first, second] = await bodies();
    expect(first?.outages).toHaveLength(MOST_OUTAGES);
    expect(second?.outages).toEqual(many.slice(MOST_OUTAGES).map(asSent));
    expect(await bodies()).toHaveLength(2);
    expect(await db.outages.count()).toBe(0);
  });
});
