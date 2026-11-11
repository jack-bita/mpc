// db.versions.test.ts — a version bump runs its upgrade (SYNC-6, 03 §6.1): a laptop full of unsent work
// moves up to the next version without losing a row, and an old version is never edited.
import Dexie, { type Transaction } from "dexie";
import { afterEach, describe, expect, it } from "vitest";

import {
  databaseName,
  openShopDatabase,
  VERSIONS,
  type ShopDatabase,
  type Version,
} from "./db";

import type { components } from "@/api/schema";

const MPC = "0192f000-0000-7000-8000-000000000001";

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

// A pretend later card: version 2 adds a `debts` drawer, and its upgrade gives every staff member a line
// owing nothing. Real later versions are added to VERSIONS in db.ts; this one lives only in the test.
// It counts its runs, so a test can see it ran once, or not at all.
let upgradesRun = 0;
const LATER: Version = {
  version: 2,
  stores: { debts: "id" },
  upgrade: async (tx: Transaction) => {
    upgradesRun += 1;
    const staff = await tx.table("staff").toArray();
    await tx
      .table("debts")
      .bulkAdd(staff.map((person) => ({ id: person.id, owes: "0" })));
  },
};

const opened: ShopDatabase[] = [];
function open(versions: readonly Version[]): ShopDatabase {
  const db = openShopDatabase(MPC, versions);
  opened.push(db);
  return db;
}
afterEach(async () => {
  for (const db of opened.splice(0)) db.close();
  await Dexie.delete(databaseName(MPC));
  upgradesRun = 0;
});

describe("the device database's versions", () => {
  it("numbers its versions 1, 2, 3… with no gap", () => {
    expect(VERSIONS.map((step) => step.version)).toEqual(
      VERSIONS.map((_, index) => index + 1),
    );
  });

  it("keeps version 1 exactly as it is", () => {
    // A laptop already on version 1 never reads it again: a drawer or search key added here would
    // reach only new laptops, and the old ones would fail at the first read of it. Never change this
    // test to make it pass; add a new version to VERSIONS instead (sync rules).
    expect(VERSIONS[0]).toEqual({
      version: 1,
      stores: {
        meta: "key",
        side: "id",
        payment_account: "id",
        staff: "id",
        setting: "id, key",
        setting_keys: "key",
        pin_checks: "staff_id",
        documents: "id, type, [type+client_time]",
        outbox: "id, &device_seq, [status+device_seq]",
        pending_effects: "id, document_id, posted_seq",
        sent_archive: "id, sent_at, device_seq",
      },
    });
  });

  it("runs version 2's upgrade on a laptop at version 1, and keeps its rows", async () => {
    const before = open(VERSIONS);
    await before.staff.put(ASHA);
    before.close();

    const after = open([...VERSIONS, LATER]);
    await after.open();

    expect(after.verno).toBe(2);
    expect(upgradesRun).toBe(1);
    expect(await after.table("debts").toArray()).toEqual([
      { id: ASHA.id, owes: "0" },
    ]);
    expect(await after.staff.get(ASHA.id)).toEqual(ASHA);
  });

  it("builds every version on a new laptop, with nothing to upgrade", async () => {
    const db = open([...VERSIONS, LATER]);
    await db.open();

    expect(db.verno).toBe(2);
    expect(upgradesRun).toBe(0);
    expect(await db.table("debts").count()).toBe(0);
  });
});
