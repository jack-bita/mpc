// sync.no-background-sync.test.ts — the page's ask for a background sync after each save (SYNC-16, 03
// §6.5), and a browser without Background Sync, which carries on as before: nothing is asked, and the
// open app's own moments send the record.
//
// jsdom has neither service workers nor Background Sync: the tests play the browser's part, with a
// stand-in registration whose sync.register they watch. Only setTimeout and setInterval are fake, as in
// sync.triggers.test.ts, so Dexie's own scheduling keeps running.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DAWA_LAPTOP } from "@/test/devices";
import { ASHA } from "@/test/shop-lists";

import { saveDocument } from "../outbox";
import { shopDatabase } from "../this-shop";
import { askForBackgroundSync, hasBackgroundSync } from "./ask-background";
import { askToSendNow } from "./asks";
import { backgroundSyncTag } from "./background";
import { CURSOR, LAST_DEVICE_SEQ } from "./meta";
import type { SyncAsk } from "./sync";
import { AFTER_A_SAVE, startSyncTriggers } from "./triggers";

const SHOP = DAWA_LAPTOP.shop.id;

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

/** The browser's part: a service worker installed, and Background Sync if `withSync`. Its register is
 * the one the tests watch. */
function aBrowser(withSync: boolean) {
  const register = vi.fn<(tag: string) => Promise<void>>(() =>
    Promise.resolve(),
  );
  const getRegistration = vi.fn(() =>
    Promise.resolve(withSync ? { sync: { register } } : {}),
  );
  Object.defineProperty(navigator, "serviceWorker", {
    value: { getRegistration },
    configurable: true,
  });
  if (withSync)
    Object.defineProperty(window, "SyncManager", {
      value: function SyncManager() {},
      configurable: true,
    });
  return { register, getRegistration };
}

async function filledLaptop(): Promise<void> {
  await shopDatabase(SHOP).meta.bulkPut([
    { key: CURSOR, value: 130 },
    { key: LAST_DEVICE_SEQ, value: 57 },
  ]);
}

const clockIn = () =>
  saveDocument(shopDatabase(SHOP), {
    type: "clock",
    schema_version: 1,
    created_by: ASHA.id,
    payload: { kind: "in", last_server_time: "2026-11-13T04:58:00Z" },
  });

// The moments a test started, stopped after it, so none runs into the next test.
let stop: () => void = () => undefined;

beforeEach(async () => {
  await filledLaptop();
  vi.useFakeTimers({ toFake: [...TIMERS] });
});

afterEach(() => {
  stop();
  vi.useRealTimers();
  vi.restoreAllMocks();
  // Back to jsdom as it is: no service workers, no Background Sync.
  delete (navigator as { serviceWorker?: unknown }).serviceWorker;
  delete (window as { SyncManager?: unknown }).SyncManager;
});

describe("a browser without Background Sync", () => {
  it("asks the browser nothing, and the open app sends the record 2 s after the save", async () => {
    // Firefox on a manager's laptop: a service worker, but no Background Sync.
    const browser = aBrowser(false);
    const sync = fakeSync();
    stop = startSyncTriggers(SHOP, sync);

    await clockIn();
    await vi.advanceTimersByTimeAsync(AFTER_A_SAVE);

    expect(hasBackgroundSync()).toBe(false);
    expect(browser.getRegistration).not.toHaveBeenCalled();
    // The one as the app opened, and the one 2 s after the save: as before SYNC-16.
    expect(sync).toHaveBeenCalledTimes(2);
  });

  it("asks nothing with no service worker at all", async () => {
    // jsdom as it is, like a browser that never installed the worker.
    await expect(askForBackgroundSync(SHOP)).resolves.toBeUndefined();
    expect(hasBackgroundSync()).toBe(false);
  });
});

describe("a browser with Background Sync", () => {
  it("asks for the shop's background sync after each save", async () => {
    const browser = aBrowser(true);
    stop = startSyncTriggers(SHOP, fakeSync());

    await clockIn();
    await vi.waitFor(() =>
      expect(browser.register).toHaveBeenCalledWith(backgroundSyncTag(SHOP)),
    );
  });

  it("asks offline too: that is when it matters", async () => {
    // Asha clocks in with no network, then closes the app: the worker sends it once the network is back.
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    const browser = aBrowser(true);
    const sync = fakeSync();
    stop = startSyncTriggers(SHOP, sync);

    await clockIn();
    await vi.waitFor(() => expect(browser.register).toHaveBeenCalledTimes(1));
    expect(sync).not.toHaveBeenCalled();
  });

  it("still sends 2 s after the save when the browser refuses the ask", async () => {
    // Background Sync switched off in the browser's settings: the open app carries on as before.
    const browser = aBrowser(true);
    browser.register.mockRejectedValue(new Error("refused"));
    const sync = fakeSync();
    stop = startSyncTriggers(SHOP, sync);

    await clockIn();
    await vi.advanceTimersByTimeAsync(AFTER_A_SAVE);

    expect(browser.register).toHaveBeenCalledTimes(1);
    expect(sync).toHaveBeenCalledTimes(2);
  });

  it("asks nothing when Tuma sasa is pressed: the open app sends at once", async () => {
    const browser = aBrowser(true);
    stop = startSyncTriggers(SHOP, fakeSync());

    askToSendNow();
    await vi.advanceTimersByTimeAsync(0);

    expect(browser.getRegistration).not.toHaveBeenCalled();
  });
});
