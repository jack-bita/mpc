// pin.changed.test.ts — a check the server's staff row no longer matches is dropped (SYNC-10, 03 §5.9):
// after a PIN change, the old PIN stops working offline once the laptop has pulled; someone who left
// loses their check the same way.
//
// Through the real pull and bootstrap, with the fake server: the drop happens in their own transaction.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { components } from "@/api/schema";
import { answer } from "@/test/fake-server";
import {
  ASHA_PIN,
  ASHA_ROW,
  ashaLoggedInOnline,
  BARAKA_PIN,
  BARAKA_ROW,
  FEW_TURNS,
  laptopWithStaff,
  PIN_CHANGED_AT,
} from "@/test/pins";
import { BOOTSTRAP } from "@/test/shop-lists";

import type { ShopDatabase } from "./db";
import { checkPinOffline, dropOutdatedChecks, rememberPin } from "./pin";
import { bootstrap } from "./sync/bootstrap";
import { pull } from "./sync/pull";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

type Change = components["schemas"]["Change"];
type StaffRecord = components["schemas"]["StaffRecord"];

/** The server's next pull page: these changes to Asha, after the laptop's cursor of 120. */
function serverSends(...changes: Change[]): void {
  answer("GET", "/api/sync/v1/pull/", {
    status: 200,
    body: {
      changes,
      cursor: 121,
      has_more: false,
      server_time: "2026-11-12T09:31:00Z",
      min_app_version: null,
    },
  });
}

function ashaNow(data: StaffRecord): Change {
  return { seq: 121, entity: "staff", id: ASHA_ROW.id, op: "upsert", data };
}

let db: ShopDatabase;
beforeEach(async () => {
  db = await laptopWithStaff();
  await ashaLoggedInOnline(db);
});
// The database itself is closed and deleted after each test (vitest.setup.ts).
afterEach(() => {
  vi.restoreAllMocks();
});

/** A sync lands while the blender runs: `sync` writes what a pull would, then the blender goes on. */
function aSyncWhileTheBlenderRuns(sync: () => Promise<unknown>): void {
  const blend = crypto.subtle.deriveBits.bind(crypto.subtle);
  vi.spyOn(crypto.subtle, "deriveBits").mockImplementationOnce(
    async (...given) => {
      await sync();
      return blend(...given);
    },
  );
}

describe("after a PIN change on the server", () => {
  it("stops the old PIN working offline once the laptop has pulled", async () => {
    // A manager gave Asha a new PIN at 09:30.
    serverSends(ashaNow({ ...ASHA_ROW, pin_changed_at: PIN_CHANGED_AT }));

    await pull(db);

    expect(await db.pin_checks.get(ASHA_ROW.id)).toBeUndefined();
    await expect(
      checkPinOffline(db, ASHA_ROW.id, ASHA_PIN),
    ).rejects.toMatchObject({ code: "pin.offline_first" });
  });

  it("still takes the old PIN before the laptop has pulled", async () => {
    // The honest limit (03 §5.9): a laptop offline since before the change can't know of it.
    expect(await checkPinOffline(db, ASHA_ROW.id, ASHA_PIN)).toEqual(ASHA_ROW);
  });

  it("drops a check whose staff row has a newer PIN, even outside a pull", async () => {
    // However the row came to differ, the check made for the old PIN is never used.
    await db.staff.put({ ...ASHA_ROW, pin_changed_at: PIN_CHANGED_AT });

    await expect(
      checkPinOffline(db, ASHA_ROW.id, ASHA_PIN),
    ).rejects.toMatchObject({ code: "pin.offline_first" });
    expect(await db.pin_checks.get(ASHA_ROW.id)).toBeUndefined();
  });

  it("drops the check when her PIN is taken away", async () => {
    serverSends(ashaNow({ ...ASHA_ROW, pin_changed_at: null }));

    await pull(db);

    expect(await db.pin_checks.get(ASHA_ROW.id)).toBeUndefined();
  });

  it("keeps the check when the pull changes only her name", async () => {
    serverSends(ashaNow({ ...ASHA_ROW, display_name: "Mama Asha" }));

    await pull(db);

    expect(await checkPinOffline(db, ASHA_ROW.id, ASHA_PIN)).toMatchObject({
      display_name: "Mama Asha",
    });
  });

  it("keeps everyone else's check", async () => {
    await rememberPin(db, BARAKA_ROW.id, BARAKA_PIN, FEW_TURNS);
    serverSends(ashaNow({ ...ASHA_ROW, pin_changed_at: PIN_CHANGED_AT }));

    await pull(db);

    expect(await checkPinOffline(db, BARAKA_ROW.id, BARAKA_PIN)).toEqual(
      BARAKA_ROW,
    );
  });
});

describe("someone who left", () => {
  it("loses their check at the pull that takes them off the laptop", async () => {
    serverSends({
      seq: 121,
      entity: "staff",
      id: ASHA_ROW.id,
      op: "archive",
      data: null,
    });

    await pull(db);

    expect(await db.pin_checks.get(ASHA_ROW.id)).toBeUndefined();
  });
});

describe("a bootstrap", () => {
  it("drops the checks its staff rows no longer match, and keeps the rest", async () => {
    await rememberPin(db, BARAKA_ROW.id, BARAKA_PIN, FEW_TURNS);
    // Filled again: Asha's PIN changed meanwhile, and Baraka's didn't.
    answer("GET", "/api/sync/v1/bootstrap/", {
      status: 200,
      body: {
        ...BOOTSTRAP,
        staff: [{ ...ASHA_ROW, pin_changed_at: PIN_CHANGED_AT }, BARAKA_ROW],
      },
    });

    await bootstrap(db);

    expect(await db.pin_checks.get(ASHA_ROW.id)).toBeUndefined();
    expect(await checkPinOffline(db, BARAKA_ROW.id, BARAKA_PIN)).toEqual(
      BARAKA_ROW,
    );
  });
});

describe("a sync while the blender runs", () => {
  // The blender takes a third of a second, outside any transaction: a pull can land in between. Each
  // re-reads the rows after it (rememberPin, lift).

  it("saves no check of a PIN whose time changed meanwhile", async () => {
    // Baraka's online yes, as a pull brings his new PIN: the one he typed may be the old one.
    aSyncWhileTheBlenderRuns(() =>
      db.staff.put({ ...BARAKA_ROW, pin_changed_at: PIN_CHANGED_AT }),
    );

    await rememberPin(db, BARAKA_ROW.id, BARAKA_PIN, FEW_TURNS);

    expect(await db.pin_checks.get(BARAKA_ROW.id)).toBeUndefined();
  });

  it("refuses the old PIN when the pull drops its check meanwhile", async () => {
    // As a pull page does: her new row, and the checks it makes outdated, in one transaction.
    aSyncWhileTheBlenderRuns(() =>
      db.transaction("rw", [db.staff, db.pin_checks], async () => {
        await db.staff.put({ ...ASHA_ROW, pin_changed_at: PIN_CHANGED_AT });
        await dropOutdatedChecks(db);
      }),
    );

    await expect(
      checkPinOffline(db, ASHA_ROW.id, ASHA_PIN),
    ).rejects.toMatchObject({ code: "pin.offline_first" });
  });

  it("refuses the old PIN when her row has a new time meanwhile, even with the check still there", async () => {
    // However the row came to differ: the PIN just checked is the old one.
    aSyncWhileTheBlenderRuns(() =>
      db.staff.put({ ...ASHA_ROW, pin_changed_at: PIN_CHANGED_AT }),
    );

    await expect(
      checkPinOffline(db, ASHA_ROW.id, ASHA_PIN),
    ).rejects.toMatchObject({ code: "pin.offline_first" });
  });

  it("refuses her when a pull takes her off the laptop meanwhile", async () => {
    aSyncWhileTheBlenderRuns(() =>
      db.transaction("rw", [db.staff, db.pin_checks], async () => {
        await db.staff.delete(ASHA_ROW.id);
        await dropOutdatedChecks(db);
      }),
    );

    await expect(
      checkPinOffline(db, ASHA_ROW.id, ASHA_PIN),
    ).rejects.toMatchObject({ code: "pin.offline_first" });
  });
});
