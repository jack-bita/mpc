// sw.sync.test.ts — the service worker's push (SYNC-16, 03 §6.5): what waits in the outbox goes when the
// browser wakes the worker, with the app closed; it takes the tabs' lock, keeps their wait after a
// failure, leaves a block as a note for the page, and tells the browser to try again later when it must.
//
// The worker's push runs here with a client of its own, made the way sw.ts makes it, over the fake
// server, with a CSRF token handed in as the Cookie Store would give it. The other tab is played through
// a stand-in lock (src/test/locks.ts).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import Dexie from "dexie";

import { createApiClient } from "@/api/make-client";
import type { components } from "@/api/schema";
import { DAWA_LAPTOP, DAWA_LAPTOP_ANSWER } from "@/test/devices";
import { answer, fakeFetch, refusal, sent } from "@/test/fake-server";
import {
  installFakeLocks,
  removeFakeLocks,
  type FakeLocks,
} from "@/test/locks";
import { ASHA } from "@/test/shop-lists";

import { databaseName } from "../db";
import { saveDocument } from "../outbox";
import { shopDatabase } from "../this-shop";
import { waitingInOrder } from "../waiting";
import {
  backgroundPush,
  backgroundSyncTag,
  listenForBackgroundSync,
  shopOfTag,
  type SyncEvent,
  TryLater,
  workerTools,
  type WorkerTools,
} from "./background";
import { mayPush } from "./backoff";
import { syncLockName } from "./lock";
import {
  CURSOR,
  LAST_DEVICE_SEQ,
  noteDeviceRefused,
  PUSH_WAIT_UNTIL,
  readDeviceRefused,
} from "./meta";

type PushedAnswer = components["schemas"]["PushedAnswer"];

const SHOP = DAWA_LAPTOP.shop.id;
const PUSH = "/api/sync/v1/push/";
const ME = "/api/devices/v1/me/";

let locks: FakeLocks;
let token: string | null;

/** The worker's tools, as sw.ts makes them: its own client, its token read at each change. */
const tools: WorkerTools = {
  api: createApiClient(
    { baseUrl: "http://shop.test", fetch: fakeFetch },
    (): Record<string, string> =>
      token === null ? {} : { "X-CSRFToken": token },
  ),
  hasCsrfToken: () => Promise.resolve(token !== null),
};

const accepted = (id: string, posted_seq: number): PushedAnswer => ({
  id,
  status: "accepted",
  first: null,
  posted_seq,
  flags: [],
  code: "",
  fields: {},
});

beforeEach(async () => {
  token = "token-from-django";
  locks = installFakeLocks();
  // A filled phone: its cursor and its last number, as a bootstrap leaves them.
  await shopDatabase(SHOP).meta.bulkPut([
    { key: CURSOR, value: 130 },
    { key: LAST_DEVICE_SEQ, value: 57 },
  ]);
  // The worker asks which shop the key belongs to before it pushes: the Dawa laptop's, MPC.
  answer("GET", ME, { status: 200, body: DAWA_LAPTOP_ANSWER });
  answer("POST", PUSH, async (request) => {
    const body = (await request.json()) as { documents: { id: string }[] };
    return Response.json({
      answers: body.documents.map((document) => accepted(document.id, 131)),
    });
  });
});

/** The pushes the worker sent: the question before each is left out. */
const pushes = () =>
  sent.filter((request) => new URL(request.url).pathname === PUSH);

afterEach(() => {
  removeFakeLocks();
});

/** Asha's clock-in, saved on the phone with no network, before the app was closed. */
const clockIn = () =>
  saveDocument(shopDatabase(SHOP), {
    type: "clock",
    schema_version: 1,
    created_by: ASHA.id,
    payload: { kind: "in", last_server_time: "2026-11-13T04:58:00Z" },
  });

const waiting = () => waitingInOrder(shopDatabase(SHOP)).count();

/** A moment for anything that was going to start. */
const aMoment = () => new Promise((resolve) => setTimeout(resolve, 20));

describe("the service worker's push", () => {
  it("sends what waits, with the CSRF token, and the outbox empties", async () => {
    const made = await clockIn();

    await backgroundPush(SHOP, tools);

    expect(pushes()).toHaveLength(1);
    const push = pushes()[0]!;
    expect(push.headers.get("X-CSRFToken")).toBe("token-from-django");
    const body = (await push.json()) as { documents: { id: string }[] };
    expect(body.documents.map((document) => document.id)).toEqual([made.id]);
    expect(await waiting()).toBe(0);
  });

  it("sends nothing when nothing waits: the open app sent it first", async () => {
    await backgroundPush(SHOP, tools);

    expect(sent).toHaveLength(0);
  });

  it("waits while a tab syncs the shop, then sends what is left", async () => {
    // The app is open after all, and its sync holds the lock: the worker waits its turn, never skips.
    await clockIn();
    const tab = locks.holdInAnotherTab(syncLockName(SHOP));
    await tab.granted;

    const worker = backgroundPush(SHOP, tools);
    await aMoment();
    expect(sent).toHaveLength(0);

    tab.release();
    await worker;
    expect(pushes()).toHaveLength(1);
  });

  it("keeps the wait after a failure, and asks the browser to try later", async () => {
    // The server is in trouble: the worker's push must not come back every few seconds either.
    await clockIn();
    answer("POST", PUSH, refusal(503, "server.unavailable"));

    await expect(backgroundPush(SHOP, tools)).rejects.toThrow();

    // The same wait the tabs read (backoff.ts): the open app's next push waits too.
    expect(await mayPush(shopDatabase(SHOP))).toBe(false);
    expect(await waiting()).toBe(1);
  });

  it("asks the browser to try later when the server says retry", async () => {
    await clockIn();
    answer("POST", PUSH, async (request) => {
      const body = (await request.json()) as { documents: { id: string }[] };
      return Response.json({
        answers: [
          {
            id: body.documents[0]!.id,
            status: "retry",
            first: null,
            posted_seq: null,
            flags: [],
            code: "",
            fields: {},
          } satisfies PushedAnswer,
        ],
      });
    });

    await expect(backgroundPush(SHOP, tools)).rejects.toBeInstanceOf(TryLater);
    expect(await mayPush(shopDatabase(SHOP))).toBe(false);
  });

  it("sends nothing during a wait, and asks the browser to try later", async () => {
    // A worker the browser woke is no one pressing Tuma sasa: the wait holds.
    await clockIn();
    await shopDatabase(SHOP).meta.put({
      key: PUSH_WAIT_UNTIL,
      value: Date.now() + 60_000,
    });

    await expect(backgroundPush(SHOP, tools)).rejects.toBeInstanceOf(TryLater);
    expect(sent).toHaveLength(0);
  });

  it("sends nothing with no CSRF token, and uses up none of the browser's tries", async () => {
    // Sent with none, the push would be refused (403). Only the app gets a token back, as it opens, so
    // a later try of the browser's would find none either: it ends quietly.
    await clockIn();
    token = null;

    await expect(backgroundPush(SHOP, tools)).resolves.toBeUndefined();
    expect(sent).toHaveLength(0);
  });

  it("leaves a block as a note for the page, and doesn't try again", async () => {
    // The manager blocked the phone while the app was closed. The worker has no localStorage.
    await clockIn();
    answer("POST", PUSH, refusal(401, "device.blocked"));

    await backgroundPush(SHOP, tools);

    expect(await readDeviceRefused(shopDatabase(SHOP))).toBe("device.blocked");
    // The records stay, so an unblock finds them still there.
    expect(await waiting()).toBe(1);
  });

  it('leaves a "not registered" as a note too, and doesn\'t try again', async () => {
    // The key opens no device any more: the page must forget its copy, and the worker can't tell it.
    await clockIn();
    answer("GET", ME, refusal(401, "not_authenticated"));

    await expect(backgroundPush(SHOP, tools)).resolves.toBeUndefined();

    expect(await readDeviceRefused(shopDatabase(SHOP))).toBe(
      "not_authenticated",
    );
    expect(pushes()).toHaveLength(0);
    expect(await waiting()).toBe(1);
  });

  it("asks nothing once a block was heard, until the page takes the note", async () => {
    await clockIn();
    await noteDeviceRefused(shopDatabase(SHOP), "device.blocked");

    await backgroundPush(SHOP, tools);

    expect(sent).toHaveLength(0);
  });
});

describe("the shop the push is for", () => {
  it("sends nothing when the browser's key now belongs to another shop", async () => {
    // A retry the browser kept for minutes, and the laptop paired to another shop in between: the Dawa
    // shop's clock-in must not be sent as the other shop's.
    await clockIn();
    answer("GET", ME, {
      status: 200,
      body: {
        ...DAWA_LAPTOP_ANSWER,
        shop: {
          ...DAWA_LAPTOP_ANSWER.shop,
          id: "019a5e00-0000-7000-8000-0000000000a2",
        },
      },
    });

    await backgroundPush(SHOP, tools);

    expect(pushes()).toHaveLength(0);
    expect(await waiting()).toBe(1);
  });

  it("leaves a block heard on the question as a note, and sends nothing", async () => {
    await clockIn();
    answer("GET", ME, refusal(401, "device.blocked"));

    await backgroundPush(SHOP, tools);

    expect(pushes()).toHaveLength(0);
    expect(await readDeviceRefused(shopDatabase(SHOP))).toBe("device.blocked");
  });
});

describe("a shop with no database here", () => {
  it("is left alone: no push, and no empty database made", async () => {
    // A stale name, from before the site's data was wiped or the laptop paired again.
    const gone = "019a5e00-0000-7000-8000-0000000000a9";

    await backgroundPush(gone, tools);

    expect(sent).toHaveLength(0);
    expect(await Dexie.exists(databaseName(gone))).toBe(false);
  });
});

describe("the worker's wiring (sw.ts)", () => {
  /** A stand-in for the worker's `self`: it keeps the listener, so a test can wake it as the browser
   * would. */
  function aWorker() {
    let listener: ((event: SyncEvent) => void) | undefined;
    const scope = {
      addEventListener: (_type: "sync", given: (event: SyncEvent) => void) => {
        listener = given;
      },
    };
    const wake = (tag: string) => {
      const waitUntil = vi.fn<(work: Promise<unknown>) => void>();
      listener!({ tag, waitUntil });
      return waitUntil;
    };
    return { scope, wake };
  }

  it("pushes the shop the sync names, and keeps the worker alive until it ends", async () => {
    await clockIn();
    const worker = aWorker();
    listenForBackgroundSync(worker.scope, tools);

    const waitUntil = worker.wake(backgroundSyncTag(SHOP));

    expect(waitUntil).toHaveBeenCalledTimes(1);
    await waitUntil.mock.calls[0]![0];
    expect(pushes()).toHaveLength(1);
  });

  it("leaves a sync that isn't ours alone", () => {
    const worker = aWorker();
    listenForBackgroundSync(worker.scope, tools);

    expect(worker.wake("someone-else")).not.toHaveBeenCalled();
  });

  it("reads the CSRF token from the Cookie Store at each change", async () => {
    // The worker has no document.cookie: the browser's Cookie Store gives it Django's csrftoken.
    await clockIn();
    const cookies = {
      get: vi.fn((name: string) =>
        Promise.resolve(
          name === "csrftoken" ? { value: "token-from-the-store" } : null,
        ),
      ),
    };
    const fromTheStore = workerTools(cookies, {
      baseUrl: "http://shop.test",
      fetch: fakeFetch,
    });

    expect(await fromTheStore.hasCsrfToken()).toBe(true);
    await backgroundPush(SHOP, fromTheStore);
    expect(pushes()[0]!.headers.get("X-CSRFToken")).toBe(
      "token-from-the-store",
    );
  });

  it("finds no token with no Cookie Store, so it pushes nothing", async () => {
    expect(await workerTools(undefined).hasCsrfToken()).toBe(false);
  });
});

describe("a background sync's name", () => {
  it("carries the shop's id, as the worker has no saved device", () => {
    expect(shopOfTag(backgroundSyncTag(SHOP))).toBe(SHOP);
  });

  it("is ours only with our start and a shop", () => {
    expect(shopOfTag("mpc-sync-")).toBeNull();
    expect(shopOfTag("someone-else")).toBeNull();
  });
});
