// sync.outages.test.ts — what a sync tells the laptop's offline periods (SYNC-14, outages.ts): a pull that
// got its answer ends the open period; a sync that got no answer opens one, though the browser said it
// was online; a refusal, or an answer this app can't use, is the server there; and a push that lost its
// line while the pull after it worked is no cut.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { NoConnection } from "@/api/refusal";
import { DAWA_LAPTOP } from "@/test/devices";
import { giveCsrfToken } from "@/test/csrf";
import { answer, refusal } from "@/test/fake-server";
import { APP_NUMBER } from "@/lib/version";
import { ASHA, BOOTSTRAP } from "@/test/shop-lists";

import { saveDocument } from "../outbox";
import { shopDatabase } from "../this-shop";
import { WrongShop } from "./bootstrap";
import { CURSOR, LAST_DEVICE_SEQ } from "./meta";
import { noteCutOff } from "./outages";
import { AppTooOld } from "./pull";
import { syncShop } from "./sync";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

const SHOP = DAWA_LAPTOP.shop.id;
const PULL = "/api/sync/v1/pull/";
const PUSH = "/api/sync/v1/push/";
const BOOTSTRAP_ROUTE = "/api/sync/v1/bootstrap/";

const emptyPage = {
  status: 200,
  body: {
    changes: [],
    cursor: 130,
    has_more: false,
    server_time: "2026-11-14T10:15:00Z",
    min_app_version: 1,
  },
};

/** What the line does: the browser's fetch fails with no answer at all (NoConnection, make-client.ts). */
const noAnswer = () => {
  throw new TypeError("Failed to fetch");
};

beforeEach(async () => {
  giveCsrfToken();
  // A filled laptop: its cursor and its last number, as a bootstrap leaves them.
  await shopDatabase(SHOP).meta.bulkPut([
    { key: CURSOR, value: 130 },
    { key: LAST_DEVICE_SEQ, value: 57 },
  ]);
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

const db = () => shopDatabase(SHOP);
const openPeriods = async () =>
  (await db().outages.toArray()).filter((row) => row.ended_at === null);

describe("a sync", () => {
  it("opens a period when it gets no answer, though the browser says it is online", async () => {
    // The router is on but its mobile data is gone: navigator.onLine is true, and nothing answers.
    answer("POST", PUSH, noAnswer);
    answer("GET", PULL, noAnswer);

    await expect(syncShop(SHOP)).rejects.toBeInstanceOf(NoConnection);

    expect(await openPeriods()).toHaveLength(1);
  });

  it("ends the open period once its pull gets an answer", async () => {
    await noteCutOff(db(), Date.now());
    answer("POST", PUSH, { status: 200, body: { answers: [] } });
    answer("GET", PULL, emptyPage);

    await syncShop(SHOP);

    expect(await openPeriods()).toHaveLength(0);
    expect(await db().outages.count()).toBe(1);
  });

  it("takes a refusal for the server being there", async () => {
    // A 500 from the server: the line works, the server has its own trouble.
    await noteCutOff(db(), Date.now());
    answer("POST", PUSH, { status: 200, body: { answers: [] } });
    answer("GET", PULL, refusal(500, "server_error"));

    await expect(syncShop(SHOP)).rejects.toThrow();

    expect(await openPeriods()).toHaveLength(0);
  });

  it("takes an answer this app can't use, too old for the server, for the server being there", async () => {
    // The server now serves app number 2 and up: the pull stops (AppTooOld), but it got an answer.
    await noteCutOff(db(), Date.now());
    answer("POST", PUSH, { status: 200, body: { answers: [] } });
    answer("GET", PULL, {
      status: 200,
      body: { ...emptyPage.body, min_app_version: APP_NUMBER + 1 },
    });

    await expect(syncShop(SHOP)).rejects.toBeInstanceOf(AppTooOld);

    expect(await openPeriods()).toHaveLength(0);
  });

  it("takes another shop's copy for the server being there", async () => {
    // A laptop paired to another shop since it last asked: the bootstrap's copy is that shop's (WrongShop),
    // and nothing is filled; but the server answered.
    await db().meta.delete(CURSOR);
    await noteCutOff(db(), Date.now());
    answer("GET", BOOTSTRAP_ROUTE, {
      status: 200,
      body: { ...BOOTSTRAP, shop: "019a5e00-0000-7000-8000-0000000000b1" },
    });

    await expect(syncShop(SHOP)).rejects.toBeInstanceOf(WrongShop);

    expect(await openPeriods()).toHaveLength(0);
  });

  it("notes no cut for a push that lost its line while the pull after it worked", async () => {
    // Asha's clock-in goes up just as the line drops, and comes back for the pull: the push's failure is
    // still thrown, so the next moment sends again, but the laptop was never cut off.
    await saveDocument(db(), {
      type: "clock",
      schema_version: 1,
      created_by: ASHA.id,
      payload: { kind: "in", last_server_time: "2026-11-14T04:58:00Z" },
    });
    answer("POST", PUSH, noAnswer);
    answer("GET", PULL, emptyPage);

    await expect(syncShop(SHOP)).rejects.toBeInstanceOf(NoConnection);

    expect(await db().outages.count()).toBe(0);
  });

  it("keeps open a cut that began after the pull was asked, as the line went again as its answer came", async () => {
    // The pull is asked at 10:05:00 and its answer arrives; at 10:05:01, before the sync notes it, the
    // router's power goes. The new cut stays open, rather than closing at once and the next moment
    // opening another for the same cut (SYNC-14's review).
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-11-14T10:05:00Z"));
    answer("POST", PUSH, { status: 200, body: { answers: [] } });
    answer("GET", PULL, async () => {
      vi.setSystemTime(new Date("2026-11-14T10:05:01Z"));
      await noteCutOff(db(), Date.now());
      return Response.json(emptyPage.body);
    });

    await syncShop(SHOP);

    expect(await openPeriods()).toEqual([
      expect.objectContaining({ started_at: "2026-11-14T10:05:01.000Z" }),
    ]);
  });

  it("goes on, and logs it, when the period can't be noted", async () => {
    // A database that refuses the write must never stop the sync, nor hide how it ended: the period
    // open, and its closing refused.
    const log = vi.spyOn(console, "error").mockImplementation(() => undefined);
    await noteCutOff(db(), Date.now());
    vi.spyOn(db().outages, "update").mockRejectedValue(new Error("disk full"));
    answer("POST", PUSH, { status: 200, body: { answers: [] } });
    answer("GET", PULL, emptyPage);

    await expect(syncShop(SHOP)).resolves.toBeUndefined();

    expect(log).toHaveBeenCalledWith(
      "the offline period was not noted",
      expect.any(Error),
    );
  });
});
