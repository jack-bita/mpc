// offline-session.test.tsx — a local session, for someone the laptop let in with no network (SYNC-10,
// 03 §5.9): every screen sees it, and it lasts only while the laptop's copy still lets the person in.
import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { saveBlocked, saveDevice } from "@/features/devices/this-device";
import { shopDatabase } from "@/offline/this-shop";
import { DAWA_LAPTOP } from "@/test/devices";
import { staffRow, theLaptopKnows } from "@/test/laptop";

import {
  endOfflineSession,
  startOfflineSession,
  useOfflinePerson,
  useOfflineSession,
} from "./offline-session";

// Fake people: made-up names.
const ASHA = staffRow(
  "019a5e00-0000-7000-8000-0000000000c2",
  "Asha Mfano",
  "Asha",
);
const JUMA = staffRow(
  "019a5e00-0000-7000-8000-0000000000c3",
  "Juma Mfano",
  "Juma",
);

const db = () => shopDatabase(DAWA_LAPTOP.shop.id);

// The Dawa laptop, registered, with both on its copy.
beforeEach(async () => {
  saveDevice(DAWA_LAPTOP);
  await theLaptopKnows(ASHA, JUMA);
});

/** Asha, let in offline: the person the hook gives, once her row is read. */
async function ashaIsHere() {
  const hook = renderHook(() => useOfflinePerson());
  act(() => startOfflineSession(ASHA));
  await waitFor(() => expect(hook.result.current?.id).toBe(ASHA.id));
  return hook;
}

describe("a local session", () => {
  it("is seen by every screen, and ends for all of them", () => {
    const one = renderHook(() => useOfflineSession());
    const two = renderHook(() => useOfflineSession());

    act(() => startOfflineSession(ASHA));
    expect(one.result.current?.staffId).toBe(ASHA.id);
    expect(two.result.current?.staffId).toBe(ASHA.id);

    act(() => endOfflineSession());
    expect(one.result.current).toBeNull();
    expect(two.result.current).toBeNull();
  });

  it("gives the person as the laptop's copy has them now", async () => {
    const { result } = await ashaIsHere();

    // A pull brings her new nickname, set in the office.
    await act(() => db().staff.put({ ...ASHA, display_name: "Mama Asha" }));

    await waitFor(() => expect(result.current?.display_name).toBe("Mama Asha"));
  });

  it("ends once a sync says she is suspended", async () => {
    // X2: the server ends a suspended person's session at the next click, and so does the laptop.
    const { result } = await ashaIsHere();

    await act(() => db().staff.put({ ...ASHA, status: "suspended" }));

    await waitFor(() => expect(result.current).toBeUndefined());
    expect(renderHook(() => useOfflineSession()).result.current).toBeNull();
  });

  it("ends once a sync brings her a new PIN", async () => {
    // The server ends the sessions made with the old PIN (03 §5.9), and so does the laptop.
    const { result } = await ashaIsHere();

    await act(() =>
      db().staff.put({ ...ASHA, pin_changed_at: "2026-11-12T09:30:00Z" }),
    );

    await waitFor(() => expect(result.current).toBeUndefined());
  });

  it("ends once a sync takes her off the laptop", async () => {
    // She left, or was switched off.
    const { result } = await ashaIsHere();

    await act(() => db().staff.delete(ASHA.id));

    await waitFor(() => expect(result.current).toBeUndefined());
  });

  it("lets the next person in after the last one, with no read of the last one ending it", async () => {
    // Badilisha mtu: Asha ends, Juma starts at once. The hook's read for Asha must not end his.
    const { result } = await ashaIsHere();

    act(() => {
      endOfflineSession();
      startOfflineSession(JUMA);
    });

    await waitFor(() => expect(result.current?.id).toBe(JUMA.id));
  });

  it("ends with a block of the laptop, so an unblock brings nobody back", async () => {
    // The block's lock covers every page; unblocked in this same tab, Asha must type her PIN again.
    const { result } = renderHook(() => useOfflineSession());
    act(() => startOfflineSession(ASHA));

    act(() => saveBlocked());
    expect(result.current).toBeNull();
    act(() => saveDevice(DAWA_LAPTOP));
    expect(result.current).toBeNull();
  });

  it("ends when the laptop is forgotten, or paired again as another device", () => {
    const { result } = renderHook(() => useOfflineSession());
    act(() => startOfflineSession(ASHA));
    act(() =>
      saveDevice({
        ...DAWA_LAPTOP,
        id: "019a5e00-0000-7000-8000-000000000002",
      }),
    );
    expect(result.current).toBeNull();

    act(() => {
      saveDevice(DAWA_LAPTOP);
      startOfflineSession(ASHA);
    });
    act(() => saveDevice(null));
    expect(result.current).toBeNull();
  });

  it("goes on when the device check saves the laptop again, renamed", () => {
    // The check runs every few minutes, online: it must never end the session of the person at work.
    const { result } = renderHook(() => useOfflineSession());
    act(() => startOfflineSession(ASHA));

    act(() => saveDevice({ ...DAWA_LAPTOP, name: "Laptop ya Dawa" }));

    expect(result.current?.staffId).toBe(ASHA.id);
  });

  it("gives nobody while there is none", async () => {
    const { result } = renderHook(() => useOfflinePerson());

    await waitFor(() => expect(result.current).toBeUndefined());
  });
});
