// pin.suspended.test.ts — a person suspended on the server can't log in offline once the laptop has
// pulled it (SYNC-10, X2, 03 §5.9). She is told so with no check, as the server tells her, and her
// wrong tries then lock nothing for later.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { components } from "@/api/schema";
import { answer } from "@/test/fake-server";
import {
  ASHA_PIN,
  ASHA_ROW,
  ashaLoggedInOnline,
  laptopWithStaff,
} from "@/test/pins";

import type { ShopDatabase } from "./db";
import { checkPinOffline } from "./pin";
import { pull } from "./sync/pull";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

type StaffRecord = components["schemas"]["StaffRecord"];

/** The server's next pull page: Asha's row as it is now. A suspended person comes with no keys. */
function serverSays(asha: StaffRecord, cursor = 121): void {
  answer("GET", "/api/sync/v1/pull/", {
    status: 200,
    body: {
      changes: [
        {
          seq: cursor,
          entity: "staff",
          id: ASHA_ROW.id,
          op: "upsert",
          data: asha,
        },
      ],
      cursor,
      has_more: false,
      server_time: "2026-11-12T09:31:00Z",
      min_app_version: null,
    },
  });
}

const SUSPENDED: StaffRecord = { ...ASHA_ROW, status: "suspended" };

let db: ShopDatabase;
beforeEach(async () => {
  db = await laptopWithStaff();
  await ashaLoggedInOnline(db);
});
// The database itself is closed and deleted after each test (vitest.setup.ts).
afterEach(() => {
  vi.restoreAllMocks();
});

describe("a suspended person", () => {
  it("can't log in offline once the laptop has pulled her suspension", async () => {
    serverSays(SUSPENDED);

    await pull(db);

    await expect(
      checkPinOffline(db, ASHA_ROW.id, ASHA_PIN),
    ).rejects.toMatchObject({ code: "staff.suspended" });
  });

  it("is told so with no check, and her tries are not counted", async () => {
    serverSays(SUSPENDED);
    await pull(db);
    const blender = vi.spyOn(crypto.subtle, "deriveBits");

    for (let i = 0; i < 6; i++)
      await expect(
        checkPinOffline(db, ASHA_ROW.id, "2581"),
      ).rejects.toMatchObject({ code: "staff.suspended" });

    expect(blender).not.toHaveBeenCalled();
    expect((await db.pin_checks.get(ASHA_ROW.id))?.wrong_tries).toBe(0);
  });

  it("still logs in before the laptop has pulled", async () => {
    // The honest limit (X2): what she does offline then is flagged on the server, at the push.
    expect(await checkPinOffline(db, ASHA_ROW.id, ASHA_PIN)).toEqual(ASHA_ROW);
  });

  it("logs in offline again once she is back at work", async () => {
    // Suspended, then back: her PIN didn't change, so the check made before still holds.
    serverSays(SUSPENDED);
    await pull(db);
    serverSays(ASHA_ROW, 122);
    await pull(db);

    expect(await checkPinOffline(db, ASHA_ROW.id, ASHA_PIN)).toEqual(ASHA_ROW);
  });
});

describe("a suspension while the blender runs", () => {
  it("refuses her right PIN, as the pull lands in the middle of its check", async () => {
    // The blender takes a third of a second, outside any transaction; the row is read again after it.
    const blend = crypto.subtle.deriveBits.bind(crypto.subtle);
    vi.spyOn(crypto.subtle, "deriveBits").mockImplementationOnce(
      async (...given) => {
        await db.staff.put(SUSPENDED);
        return blend(...given);
      },
    );

    await expect(
      checkPinOffline(db, ASHA_ROW.id, ASHA_PIN),
    ).rejects.toMatchObject({ code: "staff.suspended" });
  });
});
