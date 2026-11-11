// pull.apply.test.ts — pull pages applied on the laptop (SYNC-7, 03 §6.4): each page whole, with its
// cursor, in one transaction; the clock offset kept; pending effects dropped once counted on the server;
// and a page the app can't read changes nothing.
import Dexie from "dexie";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { components } from "@/api/schema";
import { ApiRefusal } from "@/api/refusal";
import {
  saveDevice,
  savedBlocked,
  savedDevice,
} from "@/features/devices/this-device";
import { DAWA_LAPTOP } from "@/test/devices";
import { answer, refusal, sent } from "@/test/fake-server";
import { ASHA, DAWA_SIDE, IDLE_15, IDLE_RULE } from "@/test/shop-lists";

import { openShopDatabase, type ShopDatabase } from "../db";
import { ruleInForce } from "../rules";
import { CLOCK_OFFSET, CURSOR, LAST_SERVER_TIME, readCursor } from "./meta";
import { AppTooOld, pull } from "./pull";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

type Change = components["schemas"]["Change"];
type Page = components["schemas"]["PullAnswer"];

const PULL = "/api/sync/v1/pull/";
const SERVER_TIME = "2026-11-11T09:00:00Z";

/** A page as the server sends it, with nothing more waiting unless a test says so. */
function page(changes: Change[], cursor: number, hasMore = false): Page {
  return {
    changes,
    cursor,
    has_more: hasMore,
    server_time: SERVER_TIME,
    min_app_version: null,
  };
}

/** The pages the server gives, one per pull call, in order; each request's cursor is kept. */
const askedFrom: (string | null)[] = [];
function serverGives(...pages: Page[]): void {
  answer("GET", PULL, (request) => {
    askedFrom.push(new URL(request.url).searchParams.get("cursor"));
    const next = pages.shift();
    return next
      ? Response.json(next)
      : Response.json({ code: "unexpected" }, { status: 500 });
  });
}

const RENAMED = { ...ASHA, display_name: "Mama Asha" };
const renamed = (seq: number): Change => ({
  seq,
  entity: "staff",
  id: ASHA.id,
  op: "upsert",
  data: RENAMED,
});

// The Dawa laptop, bootstrapped at change 120 with Asha and the Dawa side.
let db: ShopDatabase;
beforeEach(async () => {
  db = openShopDatabase(DAWA_LAPTOP.shop.id);
  await db.staff.put(ASHA);
  await db.side.put(DAWA_SIDE);
  await db.meta.put({ key: CURSOR, value: 120 });
  askedFrom.length = 0;
});
afterEach(async () => {
  db.close();
  await Dexie.delete(db.name);
  vi.restoreAllMocks();
});

describe("a pull", () => {
  it("shows a change made in the office, and moves the cursor", async () => {
    serverGives(page([renamed(121)], 121));

    await pull(db);

    expect(await db.staff.get(ASHA.id)).toEqual(RENAMED);
    expect(await readCursor(db)).toBe(121);
    // It asked from the bootstrap's cursor.
    expect(askedFrom).toEqual(["120"]);
  });

  it("takes a record off the laptop on an archive", async () => {
    serverGives(
      page(
        [{ seq: 121, entity: "staff", id: ASHA.id, op: "archive", data: null }],
        121,
      ),
    );

    await pull(db);

    expect(await db.staff.get(ASHA.id)).toBeUndefined();
  });

  it("does nothing for an archive of a record it never had", async () => {
    const never = "019a5e00-0000-7000-8000-0000000000c9";
    serverGives(
      page(
        [{ seq: 121, entity: "staff", id: never, op: "archive", data: null }],
        121,
      ),
    );

    await pull(db);

    expect(await db.staff.toArray()).toEqual([ASHA]);
    expect(await readCursor(db)).toBe(121);
  });

  it("applies a record's lines in order, so the last one stays", async () => {
    serverGives(
      page(
        [
          renamed(121),
          { seq: 122, entity: "staff", id: ASHA.id, op: "archive", data: null },
          { seq: 123, entity: "staff", id: ASHA.id, op: "upsert", data: ASHA },
        ],
        123,
      ),
    );

    await pull(db);

    expect(await db.staff.get(ASHA.id)).toEqual(ASHA);
  });

  it("applies a change to every list", async () => {
    const closed = { ...DAWA_SIDE, is_live: false };
    const drawer = {
      id: "019a5e00-0000-7000-8000-0000000000e2",
      kind: "cash_drawer" as const,
      name: "Droo ya pili",
      provider: "",
      number: "",
      sides: [DAWA_SIDE.id],
    };
    serverGives(
      page(
        [
          {
            seq: 121,
            entity: "side",
            id: DAWA_SIDE.id,
            op: "upsert",
            data: closed,
          },
          {
            seq: 122,
            entity: "payment_account",
            id: drawer.id,
            op: "upsert",
            data: drawer,
          },
          {
            seq: 123,
            entity: "setting",
            id: IDLE_15.id,
            op: "upsert",
            data: IDLE_15,
          },
        ],
        123,
      ),
    );

    await pull(db);

    expect(await db.side.get(DAWA_SIDE.id)).toEqual(closed);
    expect(await db.payment_account.get(drawer.id)).toEqual(drawer);
    expect(await db.setting.get(IDLE_15.id)).toEqual(IDLE_15);
  });

  it("keeps a rule's same-day fix, given last, even when its id is the smaller", async () => {
    // The manager saved 50, then fixed it to 15 the same day, on a phone whose clock is behind: the fix's
    // id, made on that phone, sorts before the typo's. The server read the fix as the one saved last, and
    // the laptop holds the row it was given last.
    const typo = {
      ...IDLE_15,
      id: "019a5e00-0000-7000-8000-000000000105",
      effective_from: "2026-11-11",
      value: "50",
    };
    const fix = {
      ...typo,
      id: "019a5e00-0000-7000-8000-000000000102",
      value: "15",
    };
    serverGives(
      page(
        [
          {
            seq: 121,
            entity: "setting",
            id: typo.id,
            op: "upsert",
            data: typo,
          },
        ],
        121,
        true,
      ),
      page(
        [{ seq: 122, entity: "setting", id: fix.id, op: "upsert", data: fix }],
        122,
      ),
    );

    await pull(db);

    expect(await db.setting.toArray()).toEqual([fix]);
    expect(
      ruleInForce(await db.setting.toArray(), IDLE_RULE, null, "2026-11-11"),
    ).toBe("15");
  });

  it("keeps a rule's rows of other days and sides beside a fix", async () => {
    const dawaRow = {
      ...IDLE_15,
      id: "019a5e00-0000-7000-8000-000000000103",
      side: DAWA_SIDE.id,
    };
    await db.setting.bulkPut([IDLE_15, dawaRow]);
    const later = {
      ...IDLE_15,
      id: "019a5e00-0000-7000-8000-000000000104",
      effective_from: "2026-11-20",
      value: "30",
    };
    serverGives(
      page(
        [
          {
            seq: 121,
            entity: "setting",
            id: later.id,
            op: "upsert",
            data: later,
          },
        ],
        121,
      ),
    );

    await pull(db);

    expect((await db.setting.toArray()).map((row) => row.id).sort()).toEqual(
      [IDLE_15.id, dawaRow.id, later.id].sort(),
    );
  });

  it("asks again at once while more wait, from each page's cursor", async () => {
    // The middle page holds no change at all: it passed over lines of lists no laptop keeps, and still
    // says more wait. Counting the changes would stop the pull there.
    serverGives(
      page([renamed(121)], 121, true),
      page([], 140, true),
      page(
        [{ seq: 141, entity: "staff", id: ASHA.id, op: "upsert", data: ASHA }],
        141,
      ),
    );

    await pull(db);

    expect(askedFrom).toEqual(["120", "121", "140"]);
    expect(await db.staff.get(ASHA.id)).toEqual(ASHA);
    expect(await readCursor(db)).toBe(141);
  });

  it("keeps the cursor where it was when the tab closes in the middle of a page", async () => {
    // The page's second line fails as it is written, as when the tab closes: the transaction is undone,
    // so the first line's rename is gone too, and the cursor still says 120. The next pull asks for the
    // same page again.
    serverGives(
      page(
        [
          renamed(121),
          {
            seq: 122,
            entity: "side",
            id: DAWA_SIDE.id,
            op: "upsert",
            data: DAWA_SIDE,
          },
        ],
        122,
      ),
    );
    vi.spyOn(db.side, "put").mockRejectedValue(new Error("tab closed"));

    await expect(pull(db)).rejects.toThrow("tab closed");

    expect(await db.staff.get(ASHA.id)).toEqual(ASHA);
    expect(await readCursor(db)).toBe(120);
  });

  it("keeps the pages already applied when a later one fails", async () => {
    // The network drops after the first page: its changes and its cursor stay, and the next pull goes on
    // from 121.
    serverGives(page([renamed(121)], 121, true));

    await expect(pull(db)).rejects.toBeInstanceOf(ApiRefusal);

    expect(await db.staff.get(ASHA.id)).toEqual(RENAMED);
    expect(await readCursor(db)).toBe(121);
  });

  it("stops when a page says more wait but its cursor doesn't move", async () => {
    // Not a working server's page: asking again from the same cursor would never end.
    serverGives(page([], 120, true), page([], 120, true));

    await expect(pull(db)).rejects.toThrow("doesn't move on");

    expect(askedFrom).toEqual(["120"]);
  });

  it("refuses a page whose cursor goes back, and changes nothing", async () => {
    serverGives(page([renamed(119)], 119));

    await expect(pull(db)).rejects.toThrow("doesn't move on");

    expect(await db.staff.get(ASHA.id)).toEqual(ASHA);
    expect(await readCursor(db)).toBe(120);
  });

  it("keeps how far the server's clock is ahead, and its last time", async () => {
    // The laptop's clock says 08:58 while the server says 09:00: two minutes behind. An empty page
    // carries the server's time too.
    vi.spyOn(Date, "now").mockReturnValue(Date.parse("2026-11-11T08:58:00Z"));
    serverGives(page([], 120));

    await pull(db);

    expect((await db.meta.get(CLOCK_OFFSET))?.value).toBe(2 * 60 * 1000);
    expect((await db.meta.get(LAST_SERVER_TIME))?.value).toBe(SERVER_TIME);
  });

  it("keeps the last good clock offset when a page's time doesn't read", async () => {
    await db.meta.put({ key: CLOCK_OFFSET, value: 5000 });
    serverGives({ ...page([renamed(121)], 121), server_time: "not a time" });

    await pull(db);

    expect((await db.meta.get(CLOCK_OFFSET))?.value).toBe(5000);
    expect(await db.meta.get(LAST_SERVER_TIME)).toBeUndefined();
    // The changes still land.
    expect(await db.staff.get(ASHA.id)).toEqual(RENAMED);
    expect(await readCursor(db)).toBe(121);
  });

  it("drops the pending effects the cursor has passed, and keeps the rest", async () => {
    // Counted by the server now (posted at 121, and at 125, the page's cursor itself: the server's
    // numbers include the change the cursor names), not yet (posted at 130), and not yet accepted (null).
    await db.pending_effects.bulkPut([
      { id: "counted", document_id: "d1", posted_seq: 121 },
      { id: "at-cursor", document_id: "d4", posted_seq: 125 },
      { id: "later", document_id: "d2", posted_seq: 130 },
      { id: "unsent", document_id: "d3", posted_seq: null },
    ]);
    serverGives(page([renamed(121)], 125));

    await pull(db);

    expect(
      (await db.pending_effects.toArray()).map((row) => row.id).sort(),
    ).toEqual(["later", "unsent"]);
  });

  it("stops before a page naming a list the app doesn't know, and changes nothing", async () => {
    // A newer server: once the app updates, the same page comes again, so nothing is passed over.
    serverGives(
      page(
        [
          renamed(121),
          {
            seq: 122,
            entity: "product",
            id: "p1",
            op: "upsert",
            data: {},
          } as unknown as Change,
        ],
        122,
      ),
    );

    await expect(pull(db)).rejects.toEqual(new AppTooOld("product"));

    expect(await db.staff.get(ASHA.id)).toEqual(ASHA);
    expect(await readCursor(db)).toBe(120);
  });

  it("changes nothing for an upsert that brings no record", async () => {
    // Not a page this app understands: better to stop than to delete the record by mistake.
    serverGives(
      page(
        [
          renamed(121),
          { seq: 122, entity: "staff", id: ASHA.id, op: "upsert", data: null },
        ],
        122,
      ),
    );

    await expect(pull(db)).rejects.toThrow("no record");

    expect(await db.staff.get(ASHA.id)).toEqual(ASHA);
    expect(await readCursor(db)).toBe(120);
  });

  it("locks the app when the laptop is blocked, and changes nothing", async () => {
    saveDevice(DAWA_LAPTOP);
    answer("GET", PULL, refusal(401, "device.blocked"));

    await expect(pull(db)).rejects.toBeInstanceOf(ApiRefusal);

    expect(savedBlocked()).toBe(true);
    expect(await readCursor(db)).toBe(120);
  });

  it("forgets the device when its key opens none, and changes nothing", async () => {
    saveDevice(DAWA_LAPTOP);
    answer("GET", PULL, refusal(401, "not_authenticated"));

    await expect(pull(db)).rejects.toBeInstanceOf(ApiRefusal);

    expect(savedDevice()).toBeNull();
    expect(savedBlocked()).toBe(false);
    expect(await readCursor(db)).toBe(120);
  });

  it("refuses to run on a laptop never bootstrapped", async () => {
    // A pull from 0 misses the rules' defaults: never a stand-in for the bootstrap.
    await db.meta.delete(CURSOR);

    await expect(pull(db)).rejects.toThrow("Bootstrap");

    expect(sent).toHaveLength(0);
  });
});
