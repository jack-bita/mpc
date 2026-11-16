// attendance-on.test.tsx — whether attendance is on today, as the laptop reads its switch (ATT-2, ADR-0033): off
// until a row switches it on, from that row's day, which comes at midnight with nothing pulled; a laptop filled
// before the switch existed still reads the rows its pulls brought, with the app's own default; and only "true"
// is on.
import { act, renderHook, waitFor } from "@testing-library/react";
import Dexie from "dexie";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { saveDevice } from "@/features/devices/this-device";
import { DAWA_LAPTOP } from "@/test/devices";
import { attendanceSwitchedOn } from "@/test/laptop";

import { ATTENDANCE_SWITCH, useAttendanceOn } from "./attendance-on";
import { DAY_CHECK_EVERY } from "./clock-today";
import { databaseName } from "./db";
import { closeShopDatabases, shopDatabase } from "./this-shop";

const db = () => shopDatabase(DAWA_LAPTOP.shop.id);

/** 07:55 in Dar on Friday 13 November 2026, by the laptop's clock. */
const MORNING = new Date("2026-11-13T04:55:00Z");

// The Dawa laptop, registered, filled before ATT-2: it holds no copy of the switch's kind and default.
beforeEach(() => {
  // The pretend clock: the time and the minute's beat. The test database (fake-indexeddb) runs on setImmediate,
  // which must stay real, or its transactions never end (SYNC-10).
  vi.useFakeTimers({
    shouldAdvanceTime: true,
    toFake: ["Date", "setInterval", "clearInterval"],
  });
  vi.setSystemTime(MORNING);
  saveDevice(DAWA_LAPTOP);
});
afterEach(async () => {
  closeShopDatabases();
  await Dexie.delete(databaseName(DAWA_LAPTOP.shop.id));
  vi.useRealTimers();
});

describe("the attendance switch on the laptop", () => {
  it("is off while no row switched it on: the app's own default", async () => {
    const { result } = renderHook(() => useAttendanceOn());

    await waitFor(() => expect(result.current).toBe(false));
  });

  it("is on from a row's day, though the laptop never learned the rule", async () => {
    // A laptop filled before the release that added the switch: its pulls still bring the row.
    await attendanceSwitchedOn("2026-11-13");

    const { result } = renderHook(() => useAttendanceOn());

    await waitFor(() => expect(result.current).toBe(true));
  });

  it("stays off until the row's day comes: on from tomorrow is off today", async () => {
    await attendanceSwitchedOn("2026-11-14");

    const { result } = renderHook(() => useAttendanceOn());

    await waitFor(() => expect(result.current).toBe(false));
  });

  it("comes on at midnight with nothing pulled, on a laptop left open offline", async () => {
    // Switched on from the 14th; it is 23:59:30 on the 13th in Dar. No pull wakes the laptop: the minute's
    // beat does, and the 14th has come.
    await attendanceSwitchedOn("2026-11-14");
    vi.setSystemTime(new Date("2026-11-13T20:59:30Z"));

    const { result } = renderHook(() => useAttendanceOn());
    await waitFor(() => expect(result.current).toBe(false));

    await act(() => vi.advanceTimersByTimeAsync(DAY_CHECK_EVERY));

    await waitFor(() => expect(result.current).toBe(true));
  });

  it("takes the laptop's own copy of the rule over the app's", async () => {
    // A server whose default for the switch were on: the server's word wins wherever the laptop has it.
    await db().setting_keys.put({ ...ATTENDANCE_SWITCH, default: "true" });

    const { result } = renderHook(() => useAttendanceOn());

    await waitFor(() => expect(result.current).toBe(true));
  });

  it("reads a damaged row as off, never as a way in left open", async () => {
    await db().setting.put({
      id: "019a5e00-0000-7000-8000-00000000a7e2",
      key: ATTENDANCE_SWITCH.key,
      side: null,
      value: "ndiyo",
      effective_from: "2026-11-01",
    });

    const { result } = renderHook(() => useAttendanceOn());

    await waitFor(() => expect(result.current).toBe(false));
  });
});
