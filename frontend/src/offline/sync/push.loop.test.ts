// push.loop.test.ts — the push (SYNC-8, 03 §6.3): the outbox goes to the server in number order, up to
// 100 at a time, and each answer is read: accepted leaves the outbox, invalid is set aside and the rest
// go on, a duplicate is read as its first answer, and a retry stops the batch with the rest kept.
import Dexie from "dexie";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiRefusal, NoConnection } from "@/api/refusal";
import type { components } from "@/api/schema";
import { saveDevice, savedBlocked } from "@/features/devices/this-device";
import { APP_VERSION } from "@/lib/version";
import { DAWA_LAPTOP } from "@/test/devices";
import { answer, refusal, sent } from "@/test/fake-server";
import { ASHA } from "@/test/shop-lists";

import { openShopDatabase, type ShopDatabase } from "../db";
import { saveDocument, type Draft, type SavedDocument } from "../outbox";
import { CURSOR, LAST_DEVICE_SEQ } from "./meta";
import { BrokenPush, push } from "./push";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

type PushedAnswer = components["schemas"]["PushedAnswer"];
type PushBody = components["schemas"]["PushBatchRequest"];

const PUSH = "/api/sync/v1/push/";

let db: ShopDatabase;
afterEach(async () => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  db.close();
  await Dexie.delete(db.name);
});

/** The Dawa laptop, filled at change 120, whose last record was #57. */
async function filledLaptop(): Promise<ShopDatabase> {
  db = openShopDatabase(DAWA_LAPTOP.shop.id);
  await db.meta.bulkPut([
    { key: CURSOR, value: 120 },
    { key: LAST_DEVICE_SEQ, value: 57 },
  ]);
  return db;
}

const CLOCK_IN: Draft = {
  type: "clock",
  schema_version: 1,
  created_by: ASHA.id,
  payload: { kind: "in", last_server_time: "2026-11-12T04:58:00Z" },
};

/** `count` clock-ins saved one after another, #58 onwards. */
async function saved(count: number): Promise<SavedDocument[]> {
  const made: SavedDocument[] = [];
  for (let i = 0; i < count; i++) made.push(await saveDocument(db, CLOCK_IN));
  return made;
}

// The four answers, in the server's shape (apps/sync/api/serializers.py, PushedAnswer).
const accepted = (id: string, posted_seq: number): PushedAnswer => ({
  id,
  status: "accepted",
  first: null,
  posted_seq,
  flags: [],
  code: "",
  fields: {},
});
const invalid = (id: string, code: string): PushedAnswer => ({
  id,
  status: "invalid",
  first: null,
  posted_seq: null,
  flags: [
    { id: "019a7000-0000-7000-8000-00000000f001", kind: "invalid_document" },
  ],
  code,
  fields: {},
});
const retry = (id: string): PushedAnswer => ({
  id,
  status: "retry",
  first: null,
  posted_seq: null,
  flags: [],
  code: "",
  fields: {},
});

/** The server accepts every document it is sent, numbering their saves from `from`. */
function acceptsAll(from = 201): void {
  let next = from;
  answer("POST", PUSH, async (request) => {
    const body = (await request.json()) as PushBody;
    return Response.json({
      answers: body.documents.map((document) => accepted(document.id, next++)),
    });
  });
}

/** What each push carried, in order. */
async function bodies(): Promise<PushBody[]> {
  return Promise.all(
    sent
      .filter((request) => new URL(request.url).pathname === PUSH)
      .map(async (request) => (await request.json()) as PushBody),
  );
}

describe("the push", () => {
  it("sends what waits in number order, never in id order", async () => {
    // Ids that run the other way from the numbers, as two laptops' clocks or a restored copy can give:
    // a push that read the outbox by id would send #60 first, and the server would flag the gap.
    await filledLaptop();
    const ids = [
      "019a7000-0000-7000-8000-0000000000c3",
      "019a7000-0000-7000-8000-0000000000b2",
      "019a7000-0000-7000-8000-0000000000a1",
    ];
    await db.documents.bulkPut(
      ids.map((id) => ({
        id,
        ...CLOCK_IN,
        client_time: "2026-11-12T05:00:00.000Z",
      })),
    );
    await db.outbox.bulkPut(
      ids.map((id, i) => ({
        id,
        type: "clock",
        device_seq: 58 + i,
        status: "waiting" as const,
        attempts: 0,
        last_error: null,
      })),
    );
    acceptsAll();

    await push(db);

    const [body] = await bodies();
    expect(body!.documents.map((document) => document.device_seq)).toEqual([
      58, 59, 60,
    ]);
    expect(body!.documents.map((document) => document.id)).toEqual(ids);
  });

  it("sends each record with its whole envelope", async () => {
    await filledLaptop();
    const [first] = await saved(1);
    acceptsAll();

    await push(db);

    const [body] = await bodies();
    expect(body!.documents).toEqual([
      {
        id: first!.id,
        type: "clock",
        schema_version: 1,
        device_seq: 58,
        client_time: first!.client_time,
        created_by: ASHA.id,
        payload: CLOCK_IN.payload,
      },
    ]);
  });

  it("moves each accepted one from the outbox to the archive, and keeps the document", async () => {
    await filledLaptop();
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-11-12T05:00:00Z"));
    const [first, second] = await saved(2);
    vi.setSystemTime(new Date("2026-11-12T06:30:00Z"));
    acceptsAll(201);

    await push(db);

    expect(await db.outbox.count()).toBe(0);
    expect(await db.sent_archive.get(first!.id)).toEqual({
      ...first,
      device_seq: 58,
      posted_seq: 201,
      sent_at: "2026-11-12T06:30:00.000Z",
    });
    expect((await db.sent_archive.get(second!.id))?.posted_seq).toBe(202);
    // The screens still read it: today's clock-ins are read from documents (SYNC-11).
    expect(await db.documents.count()).toBe(2);
  });

  it("stamps an accepted document's pending effects with its posted_seq", async () => {
    await filledLaptop();
    const made = await saveDocument(db, CLOCK_IN, [{}]);
    acceptsAll(201);

    await push(db);

    const [effect] = await db.pending_effects
      .where("document_id")
      .equals(made.id)
      .toArray();
    // Once the pull's cursor reaches 201, the server's own numbers include it, and it goes (SYNC-7).
    expect(effect?.posted_seq).toBe(201);
  });

  it("archives an accepted one that changed nothing a laptop keeps, and the rest go on", async () => {
    // The server saved it, but its save wrote nothing a laptop keeps a copy of, so no change number
    // came of it (PushedDocument.posted_seq). Nothing for a pull to bring: its effects go at once.
    await filledLaptop();
    const first = await saveDocument(db, CLOCK_IN, [{}]);
    const second = await saveDocument(db, CLOCK_IN);
    answer("POST", PUSH, {
      status: 200,
      body: {
        answers: [
          { ...accepted(first.id, 1), posted_seq: null },
          accepted(second.id, 201),
        ],
      },
    });

    expect(await push(db)).toBe("sent");

    expect(await db.outbox.count()).toBe(0);
    expect((await db.sent_archive.get(first.id))?.posted_seq).toBeNull();
    expect((await db.sent_archive.get(second.id))?.posted_seq).toBe(201);
    expect(await db.pending_effects.count()).toBe(0);
  });

  it("sends its report with it: the laptop's clock now, its version, what else waits", async () => {
    await filledLaptop();
    await saved(1);
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-11-12T07:15:00Z"));
    acceptsAll();

    await push(db);

    const [body] = await bodies();
    expect(body).toMatchObject({
      sent_at: "2026-11-12T07:15:00.000Z",
      app_version: APP_VERSION,
      unsent_count: 0,
      // Recorded from SYNC-14 on.
      outages: [],
    });
  });

  it("sets an invalid one aside, and the rest go on", async () => {
    // #59 names a type the server doesn't take: it is set aside, with its reason; #58 and #60 arrive.
    await filledLaptop();
    const [first, second, third] = await saved(3);
    answer("POST", PUSH, {
      status: 200,
      body: {
        answers: [
          accepted(first!.id, 201),
          invalid(second!.id, "document.type_unknown"),
          accepted(third!.id, 202),
        ],
      },
    });

    await push(db);

    expect(await db.outbox.toArray()).toEqual([
      {
        id: second!.id,
        type: "clock",
        device_seq: 59,
        status: "needs_attention",
        attempts: 0,
        last_error: "document.type_unknown",
      },
    ]);
    expect(
      (await db.sent_archive.orderBy("device_seq").toArray()).map(
        (row) => row.device_seq,
      ),
    ).toEqual([58, 60]);
  });

  it("drops a refused one's pending effects, as the server saved nothing of it", async () => {
    // A refused sale's stock change would otherwise be counted on the laptop for good: no pull will
    // ever bring a change of it. Another record's effects stay.
    await filledLaptop();
    const refused = await saveDocument(db, CLOCK_IN, [{}]);
    const waiting = await saveDocument(db, CLOCK_IN, [{}]);
    answer("POST", PUSH, {
      status: 200,
      body: {
        answers: [
          invalid(refused.id, "document.type_unknown"),
          retry(waiting.id),
        ],
      },
    });

    await push(db);

    const left = await db.pending_effects.toArray();
    expect(left.map((effect) => effect.document_id)).toEqual([waiting.id]);
  });

  it("reads a duplicate as its first answer", async () => {
    // Both were sent before, and the answer was lost on the way back: the server says what it said then.
    await filledLaptop();
    const [first, second] = await saved(2);
    answer("POST", PUSH, {
      status: 200,
      body: {
        answers: [
          {
            ...accepted(first!.id, 150),
            status: "duplicate",
            first: "accepted",
          },
          {
            ...invalid(second!.id, "document.maker_unknown"),
            status: "duplicate",
            first: "invalid",
          },
        ],
      },
    });

    await push(db);

    expect((await db.sent_archive.get(first!.id))?.posted_seq).toBe(150);
    expect(await db.outbox.get(second!.id)).toMatchObject({
      status: "needs_attention",
      last_error: "document.maker_unknown",
    });
  });

  it("stops at a retry, and keeps it and the rest waiting, in order", async () => {
    // The server had a problem saving #59: it answers up to it, and nothing for #60.
    await filledLaptop();
    const [first, second, third] = await saved(3);
    answer("POST", PUSH, {
      status: 200,
      body: { answers: [accepted(first!.id, 201), retry(second!.id)] },
    });

    expect(await push(db)).toBe("retry");

    expect(await bodies()).toHaveLength(1);
    expect(await db.sent_archive.count()).toBe(1);
    const waiting = await db.outbox.orderBy("device_seq").toArray();
    expect(waiting.map((row) => [row.id, row.status])).toEqual([
      [second!.id, "waiting"],
      [third!.id, "waiting"],
    ]);
    // The server said "try later" to #59 once.
    expect(waiting[0]).toMatchObject({ attempts: 1, last_error: "retry" });
  });

  it("sends the laptop's clock afresh at each try", async () => {
    // A retry sent with the first try's time would show the clock as off by the wait, and every
    // offline clock-in in it as unverified (ATT-1, the card's v1.58 note).
    await filledLaptop();
    const [first] = await saved(1);
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-11-12T08:00:00Z"));
    answer("POST", PUSH, {
      status: 200,
      body: { answers: [retry(first!.id)] },
    });
    await push(db);

    vi.setSystemTime(new Date("2026-11-12T08:00:30Z"));
    acceptsAll();
    await push(db);

    expect((await bodies()).map((body) => body.sent_at)).toEqual([
      "2026-11-12T08:00:00.000Z",
      "2026-11-12T08:00:30.000Z",
    ]);
  });

  it("applies none of a batch's answers when one can't be read", async () => {
    // A duplicate naming no first answer is the server's bug: the answers already read are undone too,
    // so no row is both archived and still waiting. Sent again, each gets its answer as before.
    await filledLaptop();
    const [first, second] = await saved(2);
    answer("POST", PUSH, {
      status: 200,
      body: {
        answers: [
          accepted(first!.id, 201),
          { ...accepted(second!.id, 202), status: "duplicate", first: null },
        ],
      },
    });

    await expect(push(db)).rejects.toThrow("no first answer");

    expect(await db.sent_archive.count()).toBe(0);
    expect(
      (await db.outbox.orderBy("device_seq").toArray()).map((row) => [
        row.device_seq,
        row.status,
      ]),
    ).toEqual([
      [58, "waiting"],
      [59, "waiting"],
    ]);
  });

  it("sends 150 as 100, then 50, each saying how many else wait", async () => {
    await filledLaptop();
    await saved(150);
    acceptsAll();

    expect(await push(db)).toBe("sent");

    const [first, second] = await bodies();
    expect(first!.documents).toHaveLength(100);
    expect(first!.unsent_count).toBe(50);
    expect(second!.documents).toHaveLength(50);
    expect(second!.documents[0]?.device_seq).toBe(158);
    expect(second!.unsent_count).toBe(0);
    expect(await db.outbox.count()).toBe(0);
  });

  it("doesn't count a record set aside as unsent", async () => {
    // It reached the server, as invalid, with a flag: counted, it would hold up a drawer's approval
    // forever (M8).
    await filledLaptop();
    const [first] = await saved(3);
    await db.outbox.update(first!.id, {
      status: "needs_attention",
      last_error: "document.type_unknown",
    });
    acceptsAll();

    await push(db);

    const [body] = await bodies();
    expect(body!.documents.map((document) => document.device_seq)).toEqual([
      59, 60,
    ]);
    expect(body!.unsent_count).toBe(0);
  });

  it("sends an empty push when nothing waits, so the laptop still reports", async () => {
    await filledLaptop();
    acceptsAll();

    expect(await push(db)).toBe("sent");

    const [body] = await bodies();
    expect(body).toMatchObject({ documents: [], unsent_count: 0 });
  });

  it("locks the app when the laptop is blocked, and leaves the outbox as it is", async () => {
    // An unblock brings back the same key, so its records can still arrive (03 §5.9, step 4).
    await filledLaptop();
    saveDevice(DAWA_LAPTOP);
    await saved(2);
    const before = await db.outbox.toArray();
    answer("POST", PUSH, refusal(401, "device.blocked"));

    await expect(push(db)).rejects.toBeInstanceOf(ApiRefusal);

    expect(savedBlocked()).toBe(true);
    expect(await db.outbox.toArray()).toEqual(before);
    expect(await db.sent_archive.count()).toBe(0);
  });

  it("throws a push refused as broken as a bug, and leaves the outbox as it is", async () => {
    // A bad envelope is a bug in this code, never one document to set aside. Thrown as no answer of
    // the server's, so it reaches the console (reportSyncFailure), naming the field the server refused.
    await filledLaptop();
    await saved(1);
    const before = await db.outbox.toArray();
    answer(
      "POST",
      PUSH,
      refusal(400, "invalid", {}, { "documents.0.device_seq": ["invalid"] }),
    );

    const failure = await push(db).catch((error: unknown) => error);

    expect(failure).toBeInstanceOf(BrokenPush);
    expect(failure).not.toBeInstanceOf(ApiRefusal);
    expect((failure as BrokenPush).refusal.body.fields).toEqual({
      "documents.0.device_seq": ["invalid"],
    });
    expect(await db.outbox.toArray()).toEqual(before);
  });

  it("throws when the network is down, and leaves the outbox as it is", async () => {
    await filledLaptop();
    await saved(1);
    const before = await db.outbox.toArray();
    answer("POST", PUSH, () => {
      throw new TypeError("Failed to fetch");
    });

    await expect(push(db)).rejects.toBeInstanceOf(NoConnection);

    expect(await db.outbox.toArray()).toEqual(before);
  });
});
