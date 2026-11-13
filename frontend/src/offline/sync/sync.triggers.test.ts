// sync.triggers.test.ts — when the laptop syncs (SYNC-9, 03 §6.5): as the app opens, when the network
// comes back, 2 s after a save, every 30 s while online, and from Tuma sasa; never while the network is
// gone, the device unknown or blocked; and what a failed sync leaves.
//
// The moments are counted with a stand-in sync and a fake clock: only setTimeout and setInterval are
// fake, as Dexie's own scheduling (setImmediate) must keep running. The laptop's own tests at the end run
// the real sync against the fake server, through the hook the root layout uses.
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiRefusal, NoConnection } from "@/api/refusal";
import { saveBlocked, saveDevice } from "@/features/devices/this-device";
import { DAWA_LAPTOP } from "@/test/devices";
import { giveCsrfToken } from "@/test/csrf";
import { answer, sent } from "@/test/fake-server";
import { ASHA, BOOTSTRAP, DAWA_SIDE } from "@/test/shop-lists";

import { NeverFilled, saveDocument } from "../outbox";
import { shopDatabase } from "../this-shop";
import { askToSendNow, tellRecordSaved } from "./asks";
import { CURSOR, LAST_DEVICE_SEQ, readCursor } from "./meta";
import { AppTooOld } from "./pull";
import { BrokenPush } from "./push";
import type { SyncAsk } from "./sync";
import { appIsTooOld } from "./too-old";
import {
  AFTER_A_SAVE,
  reportSyncFailure,
  startSyncTriggers,
  SYNC_EVERY,
  useSyncTriggers,
} from "./triggers";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

const SHOP = DAWA_LAPTOP.shop.id;
const PUSH = "/api/sync/v1/push/";
const PULL = "/api/sync/v1/pull/";

const TIMERS = [
  "setTimeout",
  "clearTimeout",
  "setInterval",
  "clearInterval",
] as const;

/** A stand-in sync that only counts: each call is one moment. */
const fakeSync = () =>
  vi.fn<(shopId: string, ask?: SyncAsk) => Promise<void>>(() =>
    Promise.resolve(),
  );

/** jsdom has no network to lose: the tests play the browser's part (offline-banner.test.tsx). */
function networkGone(): void {
  vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
}

function networkBack(): void {
  vi.spyOn(navigator, "onLine", "get").mockReturnValue(true);
  window.dispatchEvent(new Event("online"));
}

const clockIn = () =>
  saveDocument(shopDatabase(SHOP), {
    type: "clock",
    schema_version: 1,
    created_by: ASHA.id,
    payload: { kind: "in", last_server_time: "2026-11-12T07:58:00Z" },
  });

async function filledLaptop(): Promise<void> {
  await shopDatabase(SHOP).meta.bulkPut([
    { key: CURSOR, value: 130 },
    { key: LAST_DEVICE_SEQ, value: 57 },
  ]);
}

// The moments a test started, stopped after it, so none runs into the next test.
let stop: () => void = () => undefined;

afterEach(() => {
  stop();
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("the moments", () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: [...TIMERS] });
  });

  it("sync once as the app opens", () => {
    const sync = fakeSync();
    stop = startSyncTriggers(SHOP, sync);

    expect(sync).toHaveBeenCalledTimes(1);
    expect(sync).toHaveBeenLastCalledWith(SHOP, undefined);
  });

  it("sync every 30 s while online, and skip the ticks while the network is gone", () => {
    const sync = fakeSync();
    stop = startSyncTriggers(SHOP, sync);

    vi.advanceTimersByTime(SYNC_EVERY - 1);
    expect(sync).toHaveBeenCalledTimes(1);
    vi.advanceTimersByTime(1);
    expect(sync).toHaveBeenCalledTimes(2);

    // Offline for two ticks: a sync could only fail, and make the next push wait longer.
    networkGone();
    vi.advanceTimersByTime(2 * SYNC_EVERY);
    expect(sync).toHaveBeenCalledTimes(2);
  });

  it("wait for the network when the app opens without it, then sync as it comes back", () => {
    networkGone();
    const sync = fakeSync();
    stop = startSyncTriggers(SHOP, sync);
    expect(sync).not.toHaveBeenCalled();

    networkBack();

    expect(sync).toHaveBeenCalledTimes(1);
  });

  it("sync 2 s after a save, once for saves close together", () => {
    // Asha clocks in, then Baraka a second later: one sync, 2 s after the first save, takes both.
    const sync = fakeSync();
    stop = startSyncTriggers(SHOP, sync);

    tellRecordSaved();
    vi.advanceTimersByTime(1000);
    tellRecordSaved();
    vi.advanceTimersByTime(AFTER_A_SAVE - 1000 - 1);
    expect(sync).toHaveBeenCalledTimes(1);
    vi.advanceTimersByTime(1);
    expect(sync).toHaveBeenCalledTimes(2);

    // A save after that starts a new wait.
    tellRecordSaved();
    vi.advanceTimersByTime(AFTER_A_SAVE);
    expect(sync).toHaveBeenCalledTimes(3);
  });

  it("keep a busy counter sending every 2 s, never waiting for a quiet moment", () => {
    // A save every half second: a wait started again at each one would never end.
    const sync = fakeSync();
    stop = startSyncTriggers(SHOP, sync);

    for (let i = 0; i < 8; i++) {
      tellRecordSaved();
      vi.advanceTimersByTime(500);
    }

    expect(sync).toHaveBeenCalledTimes(1 + 2);
  });

  it("sync 2 s after saveDocument saves a record, and not after a save it refused", async () => {
    const sync = fakeSync();
    stop = startSyncTriggers(SHOP, sync);

    // A laptop never filled refuses the save (NeverFilled): nothing new to send.
    await expect(clockIn()).rejects.toBeInstanceOf(NeverFilled);
    vi.advanceTimersByTime(AFTER_A_SAVE);
    expect(sync).toHaveBeenCalledTimes(1);

    await filledLaptop();
    await clockIn();
    vi.advanceTimersByTime(AFTER_A_SAVE);
    expect(sync).toHaveBeenCalledTimes(2);
  });

  it("send now when Tuma sasa is pressed, asking the push to skip any wait", () => {
    // That the push then skips it is the sync's to show (push.backoff.test.ts).
    const sync = fakeSync();
    stop = startSyncTriggers(SHOP, sync);

    askToSendNow();

    expect(sync).toHaveBeenCalledTimes(2);
    expect(sync).toHaveBeenLastCalledWith(SHOP, { sendNow: true });
  });

  it("send nothing for a save made just before they stop", () => {
    // Asha's save started the 2 s wait, and the laptop was blocked within it: the wait ends with them.
    const sync = fakeSync();
    stop = startSyncTriggers(SHOP, sync);

    tellRecordSaved();
    stop();
    vi.advanceTimersByTime(AFTER_A_SAVE);

    expect(sync).toHaveBeenCalledTimes(1);
  });

  it("all stop once stopped", () => {
    const sync = fakeSync();
    startSyncTriggers(SHOP, sync)();

    tellRecordSaved();
    askToSendNow();
    networkBack();
    vi.advanceTimersByTime(2 * SYNC_EVERY);

    expect(sync).toHaveBeenCalledTimes(1);
  });

  it("go on after a failed sync, which goes to the console when it is no answer of the server's", async () => {
    const log = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const bug = new TypeError("Cannot read properties of undefined");
    const sync = fakeSync().mockRejectedValueOnce(bug);
    stop = startSyncTriggers(SHOP, sync);
    await vi.waitFor(() =>
      expect(log).toHaveBeenCalledWith("sync failed", bug),
    );

    vi.advanceTimersByTime(SYNC_EVERY);

    expect(sync).toHaveBeenCalledTimes(2);
  });

  it("tell an app too old for the server, so it updates, and log nothing", async () => {
    // Not a bug: the server's minimum is above this app's number (pull.ts). The update side listens.
    const log = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const sync = fakeSync().mockRejectedValueOnce(
      new AppTooOld('No drawer for the list "product".'),
    );
    stop = startSyncTriggers(SHOP, sync);

    await vi.waitFor(() => expect(appIsTooOld()).toBe(true));
    expect(log).not.toHaveBeenCalled();
  });
});

describe("on the laptop", () => {
  beforeEach(() => {
    // A working laptop has its CSRF token, from the device check's answer: the push needs it (sync.ts).
    giveCsrfToken();
  });

  it("fill a fresh laptop's database as the app opens, then pull", async () => {
    // A change made in the office after the copy: the first pull brings it.
    saveDevice(DAWA_LAPTOP);
    const renamed = { ...DAWA_SIDE, name: "Duka la Dawa" };
    answer("GET", "/api/sync/v1/bootstrap/", { status: 200, body: BOOTSTRAP });
    // Nothing waits to go: the push before the pull is the laptop's report alone (SYNC-8).
    answer("POST", PUSH, { status: 200, body: { answers: [] } });
    answer("GET", PULL, {
      status: 200,
      body: {
        changes: [
          {
            seq: 121,
            entity: "side",
            id: DAWA_SIDE.id,
            op: "upsert",
            data: renamed,
          },
        ],
        cursor: 121,
        has_more: false,
        server_time: "2026-11-11T09:00:00Z",
        min_app_version: 1,
      },
    });

    renderHook(() => useSyncTriggers());

    const db = shopDatabase(SHOP);
    await vi.waitFor(async () => expect(await readCursor(db)).toBe(121));
    expect(await db.side.get(DAWA_SIDE.id)).toEqual(renamed);
    expect(await db.staff.toArray()).toEqual(BOOTSTRAP.staff);
  });

  it("start no sync while the device isn't registered", async () => {
    renderHook(() => useSyncTriggers());

    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(sent).toHaveLength(0);
  });

  it("send nothing for a save waiting its 2 s once the device is blocked", async () => {
    vi.useFakeTimers({ toFake: [...TIMERS] });
    saveDevice(DAWA_LAPTOP);
    await filledLaptop();
    answer("POST", PUSH, { status: 200, body: { answers: [] } });
    answer("GET", PULL, {
      status: 200,
      body: {
        changes: [],
        cursor: 130,
        has_more: false,
        server_time: "2026-11-12T08:00:00Z",
        min_app_version: 1,
      },
    });
    renderHook(() => useSyncTriggers());
    await vi.waitFor(() => expect(sent).toHaveLength(2));

    act(() => tellRecordSaved());
    act(() => saveBlocked());
    await act(() => vi.advanceTimersByTimeAsync(AFTER_A_SAVE));

    expect(sent).toHaveLength(2);
  });

  it("stop while the device is blocked, and sync at once when it is unblocked", async () => {
    saveDevice(DAWA_LAPTOP);
    await filledLaptop();
    answer("POST", PUSH, { status: 200, body: { answers: [] } });
    answer("GET", PULL, {
      status: 200,
      body: {
        changes: [],
        cursor: 130,
        has_more: false,
        server_time: "2026-11-12T08:00:00Z",
        min_app_version: 1,
      },
    });
    renderHook(() => useSyncTriggers());
    await vi.waitFor(() => expect(sent).toHaveLength(2));

    // The manager blocks the laptop (the device check heard it): no moment asks the server any more.
    act(() => saveBlocked());
    networkBack();
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(sent).toHaveLength(2);

    // Unblocked: the check names the device again, and the moments start with a sync.
    act(() => saveDevice(DAWA_LAPTOP));
    await vi.waitFor(() => expect(sent).toHaveLength(4));
  });
});

describe("a failed sync", () => {
  it("says nothing for the server's answers and a dropped network", () => {
    // Part of a shop's day: the next moment tries again.
    const log = vi.spyOn(console, "error").mockImplementation(() => undefined);

    reportSyncFailure(
      new ApiRefusal(500, {
        code: "server_error",
        message: "",
        fields: {},
        params: {},
      }),
    );
    reportSyncFailure(new NoConnection(new TypeError("Failed to fetch")));

    expect(log).not.toHaveBeenCalled();
  });

  it("goes to the console when the server refuses a push as broken", () => {
    // A bug in the sync code (SYNC-8): every later push would be refused the same way.
    const log = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const broken = new BrokenPush(
      new ApiRefusal(400, {
        code: "invalid",
        message: "",
        fields: { "documents.0.device_seq": ["invalid"] },
        params: {},
      }),
    );

    reportSyncFailure(broken);

    expect(log).toHaveBeenCalledWith("sync failed", broken);
  });
});
