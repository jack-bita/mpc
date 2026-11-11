// db.stores.test.ts — the device database's shape (SYNC-6, 03 §6.1): one database per shop, and the
// drawers every later offline card writes into.
import Dexie from "dexie";
import { afterEach, describe, expect, it } from "vitest";

import {
  databaseName,
  type DocumentRow,
  openShopDatabase,
  type OutboxRow,
  type ShopDatabase,
} from "./db";

import type { components } from "@/api/schema";

// Two made-up shops: MPC and the practice shop. Fake ids, as everywhere in the repo.
const MPC = "0192f000-0000-7000-8000-000000000001";
const PRACTICE = "0192f000-0000-7000-8000-000000000002";

const ASHA: components["schemas"]["StaffRecord"] = {
  id: "0192f000-0000-7000-8000-0000000000a1",
  full_name: "Asha Mollel",
  display_name: "Asha",
  status: "active",
  pin_changed_at: null,
  language: "sw",
  font: "default",
  permissions: { every_side: [], sides: [] },
};

function waiting(
  id: string,
  deviceSeq: number,
  status: OutboxRow["status"] = "waiting",
): OutboxRow {
  return {
    id,
    type: "clock",
    device_seq: deviceSeq,
    status,
    attempts: 0,
    last_error: null,
  };
}

function made(id: string, type: string, clientTime: string): DocumentRow {
  return {
    id,
    type,
    schema_version: 1,
    client_time: clientTime,
    created_by: ASHA.id,
    payload: {},
  };
}

// Every database a test opens is closed and deleted after it, so each test starts on a laptop that has
// never opened the app. An open database would block its own delete.
const opened: ShopDatabase[] = [];
function open(shopId: string): ShopDatabase {
  const db = openShopDatabase(shopId);
  opened.push(db);
  return db;
}
afterEach(async () => {
  for (const db of opened.splice(0)) {
    db.close();
    await Dexie.delete(db.name);
  }
});

describe("the device database", () => {
  it("is named after its shop", () => {
    expect(databaseName(MPC)).toBe(`mpc-shop-${MPC}`);
    expect(open(MPC).name).toBe(databaseName(MPC));
  });

  it("keeps each shop's rows apart: two shops, two databases", async () => {
    const mpc = open(MPC);
    const practice = open(PRACTICE);
    await mpc.staff.put(ASHA);

    expect(await mpc.staff.get(ASHA.id)).toEqual(ASHA);
    expect(await practice.staff.count()).toBe(0);
    expect(await Dexie.getDatabaseNames()).toEqual(
      expect.arrayContaining([databaseName(MPC), databaseName(PRACTICE)]),
    );
  });

  it("has every drawer of 03 §6.1, and nothing else", async () => {
    const db = open(MPC);
    await db.open();
    expect(db.tables.map((table) => table.name).sort()).toEqual(
      [
        "meta",
        "side",
        "payment_account",
        "staff",
        "setting",
        "setting_keys",
        "pin_checks",
        "documents",
        "outbox",
        "pending_effects",
        "sent_archive",
      ].sort(),
    );
  });

  it("starts at version 1", async () => {
    const db = open(MPC);
    await db.open();
    expect(db.verno).toBe(1);
  });

  it("refuses two outbox rows on one device_seq", async () => {
    // Documents leave in device_seq order and the server answers by that number (SYNC-4): two on one
    // number would mean one of them is never sent.
    const db = open(MPC);
    await db.outbox.add(waiting("0192f000-0000-7000-8000-0000000000d1", 1));
    await expect(
      db.outbox.add(waiting("0192f000-0000-7000-8000-0000000000d2", 1)),
    ).rejects.toMatchObject({ name: "ConstraintError" });
  });

  it("hands the push what is waiting, in device_seq order", async () => {
    // Saved out of order on purpose; number 2 was set aside after an `invalid` answer (SYNC-8).
    const db = open(MPC);
    await db.outbox.bulkAdd([
      waiting("0192f000-0000-7000-8000-0000000000d3", 3),
      waiting("0192f000-0000-7000-8000-0000000000d2", 2, "needs_attention"),
      waiting("0192f000-0000-7000-8000-0000000000d1", 1),
    ]);

    const next = await db.outbox
      .where("[status+device_seq]")
      .between(["waiting", Dexie.minKey], ["waiting", Dexie.maxKey])
      .toArray();

    expect(next.map((row) => row.device_seq)).toEqual([1, 3]);
  });

  it("replays the sent archive in device_seq order", async () => {
    // After a server restore, the laptop resends what it had sent (03 §6.7), in its first order.
    const db = open(MPC);
    await db.sent_archive.bulkAdd([
      {
        ...made(
          "0192f000-0000-7000-8000-0000000000e2",
          "clock",
          "2026-11-11T06:02:00.000Z",
        ),
        device_seq: 8,
        sent_at: "2026-11-11T06:03:00.000Z",
        posted_seq: 41,
      },
      {
        ...made(
          "0192f000-0000-7000-8000-0000000000e1",
          "clock",
          "2026-11-11T05:58:00.000Z",
        ),
        device_seq: 7,
        sent_at: "2026-11-11T06:03:00.000Z",
        posted_seq: 40,
      },
    ]);

    const replay = await db.sent_archive.orderBy("device_seq").toArray();

    expect(replay.map((row) => row.device_seq)).toEqual([7, 8]);
  });

  it("finds one kind of document for one day", async () => {
    // Today's clock-ins (SYNC-11): yesterday's clock-in and today's sale are left out.
    const db = open(MPC);
    await db.documents.bulkAdd([
      made(
        "0192f000-0000-7000-8000-0000000000c1",
        "clock",
        "2026-11-10T05:58:00.000Z",
      ),
      made(
        "0192f000-0000-7000-8000-0000000000c2",
        "clock",
        "2026-11-11T06:02:00.000Z",
      ),
      made(
        "0192f000-0000-7000-8000-0000000000c3",
        "sale",
        "2026-11-11T07:15:00.000Z",
      ),
    ]);

    const today = await db.documents
      .where("[type+client_time]")
      .between(
        ["clock", "2026-11-11T00:00:00.000Z"],
        ["clock", "2026-11-12T00:00:00.000Z"],
      )
      .toArray();

    expect(today.map((document) => document.id)).toEqual([
      "0192f000-0000-7000-8000-0000000000c2",
    ]);
  });
});
