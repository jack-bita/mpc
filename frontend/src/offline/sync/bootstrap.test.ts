// bootstrap.test.ts — a laptop's first full copy (SYNC-7, 03 §6.4): it fills every list and sets the
// cursor, all at once or not at all, and a refusal about the device is kept as the device check keeps it.
// It also keeps where the laptop's own count stands, so its next record carries on from it (SYNC-8).
import Dexie from "dexie";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiRefusal, NoConnection } from "@/api/refusal";
import {
  saveDevice,
  savedBlocked,
  savedDevice,
} from "@/features/devices/this-device";
import { DAWA_LAPTOP } from "@/test/devices";
import { answer, refusal, sent } from "@/test/fake-server";
import { ASHA, BOOTSTRAP, DAWA_SIDE } from "@/test/shop-lists";

import { openShopDatabase, type ShopDatabase } from "../db";
import { bootstrap, needsBootstrap } from "./bootstrap";
import { CURSOR, LAST_DEVICE_SEQ, readCursor, readLastDeviceSeq } from "./meta";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

const BOOTSTRAP_ROUTE = "/api/sync/v1/bootstrap/";

// Each test opens the Dawa laptop's database fresh, and deletes it after: a laptop that never synced.
let db: ShopDatabase;
function freshDatabase(): ShopDatabase {
  db = openShopDatabase(DAWA_LAPTOP.shop.id);
  return db;
}
afterEach(async () => {
  db.close();
  await Dexie.delete(db.name);
  vi.restoreAllMocks();
});

describe("the bootstrap", () => {
  it("fills a fresh laptop with every list, and sets the cursor", async () => {
    freshDatabase();
    answer("GET", BOOTSTRAP_ROUTE, { status: 200, body: BOOTSTRAP });
    expect(await needsBootstrap(db)).toBe(true);

    await bootstrap(db);

    expect(await db.side.toArray()).toEqual(BOOTSTRAP.side);
    expect(await db.payment_account.toArray()).toEqual(
      BOOTSTRAP.payment_account,
    );
    expect(await db.staff.toArray()).toEqual(BOOTSTRAP.staff);
    expect(await db.setting.toArray()).toEqual(BOOTSTRAP.setting);
    expect(await db.setting_keys.toArray()).toEqual(BOOTSTRAP.setting_keys);
    expect(await readCursor(db)).toBe(120);
    // Filled now: the next sync pulls instead.
    expect(await needsBootstrap(db)).toBe(false);
  });

  it("takes a shop with no changes yet, at cursor 0", async () => {
    // A shop just set up has written no change: the server answers 0, a real cursor, not "none".
    freshDatabase();
    answer("GET", BOOTSTRAP_ROUTE, {
      status: 200,
      body: { ...BOOTSTRAP, cursor: 0 },
    });

    await bootstrap(db);

    expect(await readCursor(db)).toBe(0);
    expect(await needsBootstrap(db)).toBe(false);
  });

  it("keeps the laptop's last number, so its next record carries on from it", async () => {
    // The server says this laptop's last record was #57: its next one is #58, never #1 (SYNC-8).
    freshDatabase();
    answer("GET", BOOTSTRAP_ROUTE, { status: 200, body: BOOTSTRAP });

    await bootstrap(db);

    expect(await readLastDeviceSeq(db)).toBe(57);
  });

  it("keeps its own number when filled again, if it is ahead of the server's", async () => {
    // Filled again (SYNC-13) while #58 to #70 still wait in its outbox: the server has seen only #57,
    // and counting from it would give #58 a second time.
    freshDatabase();
    await db.meta.put({ key: LAST_DEVICE_SEQ, value: 70 });
    answer("GET", BOOTSTRAP_ROUTE, { status: 200, body: BOOTSTRAP });

    await bootstrap(db);

    expect(await readLastDeviceSeq(db)).toBe(70);
  });

  it("keeps no record the server no longer sends, when filled again", async () => {
    freshDatabase();
    const left = { ...ASHA, id: "019a5e00-0000-7000-8000-0000000000c9" };
    await db.staff.put(left);
    answer("GET", BOOTSTRAP_ROUTE, { status: 200, body: BOOTSTRAP });

    await bootstrap(db);

    expect(await db.staff.toArray()).toEqual([ASHA]);
  });

  it("saves nothing when it fails halfway", async () => {
    // As a tab closed while the copy is being written: the staff list fails after the sides were
    // written, so the transaction is undone, sides too, and no cursor says the copy is whole.
    freshDatabase();
    answer("GET", BOOTSTRAP_ROUTE, { status: 200, body: BOOTSTRAP });
    vi.spyOn(db.staff, "bulkPut").mockRejectedValue(new Error("tab closed"));

    await expect(bootstrap(db)).rejects.toThrow("tab closed");

    expect(await db.side.count()).toBe(0);
    expect(await db.meta.get(CURSOR)).toBeUndefined();
    expect(await readLastDeviceSeq(db)).toBeNull();
    expect(await needsBootstrap(db)).toBe(true);
  });

  it("locks the app when the laptop is blocked, and saves nothing", async () => {
    freshDatabase();
    saveDevice(DAWA_LAPTOP);
    answer("GET", BOOTSTRAP_ROUTE, refusal(401, "device.blocked"));

    await expect(bootstrap(db)).rejects.toBeInstanceOf(ApiRefusal);

    expect(savedBlocked()).toBe(true);
    // The device stays known, so the lock can name it.
    expect(savedDevice()).toEqual(DAWA_LAPTOP);
    expect(await needsBootstrap(db)).toBe(true);
  });

  it("forgets the device when its key opens none", async () => {
    freshDatabase();
    saveDevice(DAWA_LAPTOP);
    answer("GET", BOOTSTRAP_ROUTE, refusal(401, "not_authenticated"));

    await expect(bootstrap(db)).rejects.toBeInstanceOf(ApiRefusal);

    expect(savedDevice()).toBeNull();
    expect(savedBlocked()).toBe(false);
  });

  it("keeps the device as it was when the network is down", async () => {
    freshDatabase();
    saveDevice(DAWA_LAPTOP);
    answer("GET", BOOTSTRAP_ROUTE, () => {
      throw new TypeError("Failed to fetch");
    });

    await expect(bootstrap(db)).rejects.toBeInstanceOf(NoConnection);

    expect(savedDevice()).toEqual(DAWA_LAPTOP);
    expect(savedBlocked()).toBe(false);
    expect(await needsBootstrap(db)).toBe(true);
  });

  it("asks the bootstrap route once", async () => {
    freshDatabase();
    answer("GET", BOOTSTRAP_ROUTE, { status: 200, body: BOOTSTRAP });

    await bootstrap(db);

    expect(sent.map((request) => new URL(request.url).pathname)).toEqual([
      BOOTSTRAP_ROUTE,
    ]);
    expect(await db.side.get(DAWA_SIDE.id)).toEqual(DAWA_SIDE);
  });
});
