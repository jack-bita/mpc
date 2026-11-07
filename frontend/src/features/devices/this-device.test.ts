// this-device.test.ts — the device's saved copy: kept, forgotten, never trusted when it can't be read,
// and followed by every screen at once (UI-3).
import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DAWA_LAPTOP } from "@/test/devices";

import {
  DEVICE_STORAGE_KEY,
  saveDevice,
  savedDevice,
  useThisDevice,
} from "./this-device";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("the device's saved copy", () => {
  it("is none on a new device", () => {
    expect(savedDevice()).toBeNull();
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
    // Broken text, and a copy from another version of the app, with no home side.
    for (const text of [
      "{not json",
      JSON.stringify({ ...DAWA_LAPTOP, homeSide: undefined }),
      JSON.stringify({ ...DAWA_LAPTOP, code: "1" }),
      JSON.stringify([DAWA_LAPTOP]),
      "null",
    ]) {
      window.localStorage.setItem(DEVICE_STORAGE_KEY, text);
      expect(savedDevice()).toBeNull();
    }
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
    const { result } = renderHook(() => useThisDevice());
    expect(result.current).toBeNull();

    act(() => saveDevice(DAWA_LAPTOP));
    expect(result.current).toEqual(DAWA_LAPTOP);

    act(() => saveDevice(null));
    expect(result.current).toBeNull();
  });

  it("follows a copy saved in another tab", () => {
    const { result } = renderHook(() => useThisDevice());

    // The other tab writes the copy; the browser then tells this tab with a "storage" event.
    act(() => {
      window.localStorage.setItem(
        DEVICE_STORAGE_KEY,
        JSON.stringify(DAWA_LAPTOP),
      );
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
