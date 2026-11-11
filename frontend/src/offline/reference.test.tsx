// reference.test.tsx — the live hooks for the shop's lists (SYNC-7): they read the laptop's database, and
// redraw by themselves when a pull changes it, with no reload.
import { act, renderHook, waitFor } from "@testing-library/react";
import Dexie from "dexie";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { saveDevice } from "@/features/devices/this-device";
import { DAWA_LAPTOP } from "@/test/devices";
import {
  ASHA,
  DAWA_DRAWER,
  DAWA_SIDE,
  IDLE_15,
  IDLE_RULE,
} from "@/test/shop-lists";

import { databaseName } from "./db";
import { usePaymentAccounts, useRule, useSides, useStaff } from "./reference";
import { CLOCK_OFFSET } from "./sync/meta";
import { closeShopDatabases, shopDatabase } from "./this-shop";

// The Dawa laptop, registered, with Asha, the Dawa side and its drawer, and the idle lock at 15.
beforeEach(async () => {
  saveDevice(DAWA_LAPTOP);
  const db = shopDatabase(DAWA_LAPTOP.shop.id);
  await db.staff.put(ASHA);
  await db.side.put(DAWA_SIDE);
  await db.payment_account.put(DAWA_DRAWER);
  await db.setting.put(IDLE_15);
  await db.setting_keys.put(IDLE_RULE);
});
afterEach(async () => {
  closeShopDatabases();
  await Dexie.delete(databaseName(DAWA_LAPTOP.shop.id));
  vi.useRealTimers();
});

describe("the live lists", () => {
  it("read the laptop's database", async () => {
    const { result } = renderHook(() => ({
      sides: useSides(),
      accounts: usePaymentAccounts(),
      staff: useStaff(),
    }));

    await waitFor(() =>
      expect(result.current).toEqual({
        sides: [DAWA_SIDE],
        accounts: [DAWA_DRAWER],
        staff: [ASHA],
      }),
    );
  });

  it("redraw when a pull renames someone", async () => {
    const { result } = renderHook(() => useStaff());
    await waitFor(() => expect(result.current).toEqual([ASHA]));

    // What a pull writes: Asha as she is now.
    await act(() =>
      shopDatabase(DAWA_LAPTOP.shop.id).staff.put({
        ...ASHA,
        display_name: "Mama Asha",
      }),
    );

    await waitFor(() =>
      expect(result.current?.[0]?.display_name).toBe("Mama Asha"),
    );
  });

  it("give nothing while the device isn't registered", async () => {
    saveDevice(null);

    const { result } = renderHook(() => useStaff());

    // Asked a moment later still: there is no shop to read.
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(result.current).toBeUndefined();
  });
});

describe("the live rule", () => {
  it("gives the value in force today", async () => {
    vi.useFakeTimers({
      toFake: ["Date"],
      now: Date.parse("2026-11-11T09:00:00Z"),
    });

    const { result } = renderHook(() => useRule(IDLE_RULE.key, DAWA_SIDE.id));

    await waitFor(() => expect(result.current).toBe("15"));
  });

  it("redraws when a pull brings a new row", async () => {
    vi.useFakeTimers({
      toFake: ["Date"],
      now: Date.parse("2026-11-11T09:00:00Z"),
    });
    const { result } = renderHook(() => useRule(IDLE_RULE.key, null));
    await waitFor(() => expect(result.current).toBe("15"));

    await act(() =>
      shopDatabase(DAWA_LAPTOP.shop.id).setting.put({
        ...IDLE_15,
        id: "019a5e00-0000-7000-8000-000000000102",
        effective_from: "2026-11-10",
        value: "20",
      }),
    );

    await waitFor(() => expect(result.current).toBe("20"));
  });

  it("turns to a new rule on the shop's day by the server's clock, not the laptop's", async () => {
    // A row from 12 November. The laptop's clock says 11 November, 23:00 in Arusha; the server's, a
    // pull said, is two hours ahead: already the 12th.
    vi.useFakeTimers({
      toFake: ["Date"],
      now: Date.parse("2026-11-11T20:00:00Z"),
    });
    const db = shopDatabase(DAWA_LAPTOP.shop.id);
    await db.setting.put({
      ...IDLE_15,
      id: "019a5e00-0000-7000-8000-000000000102",
      effective_from: "2026-11-12",
      value: "30",
    });
    await db.meta.put({ key: CLOCK_OFFSET, value: 2 * 60 * 60 * 1000 });

    const { result } = renderHook(() => useRule(IDLE_RULE.key, null));

    await waitFor(() => expect(result.current).toBe("30"));
  });

  it("reads the laptop's own clock when the offset kept isn't a number", async () => {
    vi.useFakeTimers({
      toFake: ["Date"],
      now: Date.parse("2026-11-11T09:00:00Z"),
    });
    await shopDatabase(DAWA_LAPTOP.shop.id).meta.put({
      key: CLOCK_OFFSET,
      value: Number.NaN,
    });

    const { result } = renderHook(() => useRule(IDLE_RULE.key, null));

    await waitFor(() => expect(result.current).toBe("15"));
  });

  it("gives nothing for a rule the laptop doesn't know", async () => {
    const { result } = renderHook(() => useRule("no.such_rule", null));

    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(result.current).toBeUndefined();
  });
});
