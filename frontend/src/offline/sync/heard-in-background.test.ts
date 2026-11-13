// heard-in-background.test.ts — a block the service worker heard reaches the page (SYNC-16, 03 §5.9):
// the worker leaves a note in the shop's database, as it has no localStorage, and the page takes it as
// the app opens, with no network too, and before each sync, which then asks the server nothing.
import { renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  saveDevice,
  savedBlocked,
  savedDevice,
} from "@/features/devices/this-device";
import { giveCsrfToken } from "@/test/csrf";
import { DAWA_LAPTOP } from "@/test/devices";
import { sent } from "@/test/fake-server";

import { shopDatabase } from "../this-shop";
import { DEVICE_REFUSED, noteDeviceRefused, readDeviceRefused } from "./meta";
import { heardInTheBackground } from "./page-place";
import { syncShop } from "./sync";
import { useSyncTriggers } from "./triggers";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

const SHOP = DAWA_LAPTOP.shop.id;

afterEach(() => {
  vi.restoreAllMocks();
});

describe("a refusal heard in the background", () => {
  it("locks the page when the worker heard a block, and the note goes", async () => {
    saveDevice(DAWA_LAPTOP);
    const db = shopDatabase(SHOP);
    await noteDeviceRefused(db, "device.blocked");

    expect(await heardInTheBackground(db)).toBe(true);

    expect(savedBlocked()).toBe(true);
    // The device is kept, so the lock can say which one the manager must unblock.
    expect(savedDevice()).toEqual(DAWA_LAPTOP);
    // Taken once: kept, it would block the laptop again after the manager's unblock.
    expect(await readDeviceRefused(db)).toBeNull();
  });

  it("forgets the device when the worker heard its key opens none", async () => {
    saveDevice(DAWA_LAPTOP);
    const db = shopDatabase(SHOP);
    await noteDeviceRefused(db, "not_authenticated");

    expect(await heardInTheBackground(db)).toBe(true);

    expect(savedDevice()).toBeNull();
    expect(savedBlocked()).toBe(false);
  });

  it("changes nothing with no note, or one it can't read", async () => {
    saveDevice(DAWA_LAPTOP);
    const db = shopDatabase(SHOP);
    expect(await heardInTheBackground(db)).toBe(false);

    await db.meta.put({ key: DEVICE_REFUSED, value: "something.else" });
    expect(await heardInTheBackground(db)).toBe(false);

    expect(savedDevice()).toEqual(DAWA_LAPTOP);
    expect(savedBlocked()).toBe(false);
  });

  it("locks the app as it opens, with no network", async () => {
    // The phone was blocked while the app was closed; it opens offline: the lock must still go on.
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    saveDevice(DAWA_LAPTOP);
    await noteDeviceRefused(shopDatabase(SHOP), "device.blocked");

    renderHook(() => useSyncTriggers());

    await vi.waitFor(() => expect(savedBlocked()).toBe(true));
    expect(sent).toHaveLength(0);
  });

  it("stops a sync before it asks the server anything", async () => {
    // Heard by the worker while this page was open: the page's next sync keeps it, and asks nothing.
    giveCsrfToken();
    saveDevice(DAWA_LAPTOP);
    await noteDeviceRefused(shopDatabase(SHOP), "device.blocked");

    await syncShop(SHOP);

    expect(savedBlocked()).toBe(true);
    expect(sent).toHaveLength(0);
  });
});
