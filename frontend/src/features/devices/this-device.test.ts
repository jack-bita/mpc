// this-device.test.ts — the device's saved copy: kept, blocked, forgotten, never trusted when it can't be
// read, and followed by every screen at once (UI-3).
import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DAWA_LAPTOP } from "@/test/devices";

import {
  DEVICE_STORAGE_KEY,
  saveBlocked,
  savedBlocked,
  saveDevice,
  savedDevice,
  useDeviceBlocked,
  useThisDevice,
} from "./this-device";

// A copy as this version of the app writes it.
const stored = (device: unknown, blocked = false) =>
  JSON.stringify({ device, blocked });

afterEach(() => {
  vi.restoreAllMocks();
});

describe("the device's saved copy", () => {
  it("is none on a new device, and not blocked", () => {
    expect(savedDevice()).toBeNull();
    expect(savedBlocked()).toBe(false);
  });

  it("keeps a device, and gives it back", () => {
    saveDevice(DAWA_LAPTOP);

    expect(savedDevice()).toEqual(DAWA_LAPTOP);
    // Kept in the browser, so a reload knows it too.
    expect(window.localStorage.getItem(DEVICE_STORAGE_KEY)).not.toBeNull();
  });

  it("forgets it", () => {
    saveDevice(DAWA_LAPTOP);

    saveDevice(null);

    expect(savedDevice()).toBeNull();
    expect(window.localStorage.getItem(DEVICE_STORAGE_KEY)).toBeNull();
  });

  it("reads a copy it can't trust as none", () => {
    // Broken text, and copies from other versions of the app, or written by hand.
    for (const text of [
      "{not json",
      "null",
      JSON.stringify(DAWA_LAPTOP),
      stored({ ...DAWA_LAPTOP, homeSide: undefined }),
      stored({ ...DAWA_LAPTOP, code: "1" }),
      stored([DAWA_LAPTOP]),
      JSON.stringify({ device: DAWA_LAPTOP, blocked: "yes" }),
    ]) {
      window.localStorage.setItem(DEVICE_STORAGE_KEY, text);
      expect(savedDevice()).toBeNull();
      expect(savedBlocked()).toBe(false);
    }
  });

  it("keeps a block, with the device it was known as", () => {
    saveDevice(DAWA_LAPTOP);

    saveBlocked();

    expect(savedBlocked()).toBe(true);
    // So the lock can say which device the manager must unblock.
    expect(savedDevice()).toEqual(DAWA_LAPTOP);
  });

  it("keeps a block on a device it never knew", () => {
    // Its saved copy was wiped, and its key still works for the server.
    saveBlocked();

    expect(savedBlocked()).toBe(true);
    expect(savedDevice()).toBeNull();
  });

  it("lifts a block when the server names the device again", () => {
    saveDevice(DAWA_LAPTOP);
    saveBlocked();

    saveDevice(DAWA_LAPTOP);

    expect(savedBlocked()).toBe(false);
  });

  it("lifts a block when the server knows no device by this key", () => {
    saveBlocked();

    saveDevice(null);

    expect(savedBlocked()).toBe(false);
    expect(window.localStorage.getItem(DEVICE_STORAGE_KEY)).toBeNull();
  });

  it("gives back the same object while nothing changed", () => {
    // React draws again without end if a store hands it a new object on every read.
    saveDevice(DAWA_LAPTOP);

    expect(savedDevice()).toBe(savedDevice());
  });

  it("writes only when something changed", () => {
    // The check runs every 5 minutes: each write would wake the app's other tabs for nothing.
    const write = vi.spyOn(Storage.prototype, "setItem");

    saveDevice(DAWA_LAPTOP);
    saveDevice({ ...DAWA_LAPTOP });

    expect(write).toHaveBeenCalledTimes(1);
  });

  it("is followed by every screen at once", () => {
    const { result } = renderHook(() => ({
      device: useThisDevice(),
      blocked: useDeviceBlocked(),
    }));
    expect(result.current).toEqual({ device: null, blocked: false });

    act(() => saveDevice(DAWA_LAPTOP));
    expect(result.current).toEqual({ device: DAWA_LAPTOP, blocked: false });

    act(() => saveBlocked());
    expect(result.current).toEqual({ device: DAWA_LAPTOP, blocked: true });

    act(() => saveDevice(null));
    expect(result.current).toEqual({ device: null, blocked: false });
  });

  it("follows a copy saved in another tab", () => {
    const { result } = renderHook(() => useThisDevice());

    // The other tab writes the copy; the browser then tells this tab with a "storage" event.
    act(() => {
      window.localStorage.setItem(DEVICE_STORAGE_KEY, stored(DAWA_LAPTOP));
      window.dispatchEvent(
        new StorageEvent("storage", { key: DEVICE_STORAGE_KEY }),
      );
    });

    expect(result.current).toEqual(DAWA_LAPTOP);
  });

  it("knows no device, and breaks nothing, when the browser refuses its storage", () => {
    const refuse = () => {
      throw new DOMException("Storage is blocked", "SecurityError");
    };
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(refuse);
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(refuse);

    expect(() => saveDevice(DAWA_LAPTOP)).not.toThrow();
    expect(savedDevice()).toBeNull();
  });
});
