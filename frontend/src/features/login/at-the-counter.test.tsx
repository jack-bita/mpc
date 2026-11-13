// at-the-counter.test.tsx — the counter's note of who is logged in at this laptop (SYNC-11, 03 §5.9):
// every counter screen reads it without asking the server, and it holds only while the laptop's copy
// still lets the person in.
import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { saveBlocked, saveDevice } from "@/features/devices/this-device";
import { shopDatabase } from "@/offline/this-shop";
import { DAWA_LAPTOP } from "@/test/devices";
import { staffRow, theLaptopKnows } from "@/test/laptop";

import {
  arriveAtCounter,
  askToLeave,
  leaveHeard,
  nobodyAtCounter,
  useAtTheCounter,
  useLeaveAsked,
  usePersonAtCounter,
} from "./at-the-counter";

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

/** The shop's idle minutes, as the home page hands them over with the person. */
const IDLE_MINUTES = 15;

const db = () => shopDatabase(DAWA_LAPTOP.shop.id);

// The Dawa laptop, registered, with both on its copy.
beforeEach(async () => {
  saveDevice(DAWA_LAPTOP);
  await theLaptopKnows(ASHA, JUMA);
});

/** Asha, logged in at the home page, as a counter screen reads her once her row is read. */
async function ashaIsHere() {
  const hook = renderHook(() => usePersonAtCounter());
  act(() => arriveAtCounter(ASHA, IDLE_MINUTES, "server"));
  await waitFor(() => expect(hook.result.current?.row.id).toBe(ASHA.id));
  return hook;
}

describe("the counter's note of who is here", () => {
  it("is read by every screen, and gone for all of them once nobody is here", () => {
    const one = renderHook(() => useAtTheCounter());
    const two = renderHook(() => useAtTheCounter());

    act(() => arriveAtCounter(ASHA, IDLE_MINUTES, "server"));
    expect(one.result.current?.staffId).toBe(ASHA.id);
    expect(two.result.current?.staffId).toBe(ASHA.id);

    act(() => nobodyAtCounter());
    expect(one.result.current).toBeNull();
    expect(two.result.current).toBeNull();
  });

  it("gives the person as the laptop's copy has them now, and the idle minutes it was given", async () => {
    const { result } = await ashaIsHere();
    expect(result.current?.idleMinutes).toBe(IDLE_MINUTES);

    // A pull brings her new nickname, set in the office.
    await act(() => db().staff.put({ ...ASHA, display_name: "Mama Asha" }));

    await waitFor(() =>
      expect(result.current?.row.display_name).toBe("Mama Asha"),
    );
  });

  it("says nobody with no note, and that it is still reading until the person's row is read", async () => {
    // Two answers a screen must tell apart: nobody (null) sends it back to the name tiles; still reading
    // (undefined) only waits. Read as one, a screen would send Asha away while her row is on its way.
    const { result } = renderHook(() => usePersonAtCounter());
    expect(result.current).toBeNull();

    act(() => arriveAtCounter(ASHA, IDLE_MINUTES, "server"));
    expect(result.current).toBeUndefined();

    await waitFor(() => expect(result.current?.row.id).toBe(ASHA.id));
  });

  it("is nobody once a sync says she is suspended", async () => {
    // X2: the server ends a suspended person's session at the next click. A counter screen never
    // clicks on the server, so the laptop's copy must end it here.
    const { result } = await ashaIsHere();

    await act(() => db().staff.put({ ...ASHA, status: "suspended" }));

    await waitFor(() => expect(result.current).toBeNull());
    expect(renderHook(() => useAtTheCounter()).result.current).toBeNull();
  });

  it("is nobody once a sync brings her a new PIN", async () => {
    // A new PIN is set when the old one leaked: whoever logged in with the old one must not go on
    // making records in her name (03 §5.9).
    const { result } = await ashaIsHere();

    await act(() =>
      db().staff.put({ ...ASHA, pin_changed_at: "2026-11-12T09:30:00Z" }),
    );

    await waitFor(() => expect(result.current).toBeNull());
  });

  it("is nobody once a sync takes her off the laptop", async () => {
    // She left, or was switched off.
    const { result } = await ashaIsHere();

    await act(() => db().staff.delete(ASHA.id));

    await waitFor(() => expect(result.current).toBeNull());
  });

  it("lets the next person in after the last one, with no read of the last one ending it", async () => {
    // Badilisha mtu: Asha goes, Juma arrives at once. The hook's read for Asha must not end his.
    const { result } = await ashaIsHere();

    act(() => {
      nobodyAtCounter();
      arriveAtCounter(JUMA, IDLE_MINUTES, "server");
    });

    await waitFor(() => expect(result.current?.row.id).toBe(JUMA.id));
  });

  it("goes with a block of the laptop, so an unblock brings nobody back", () => {
    // The block's lock covers every page; unblocked in this same tab, the counter must not open on
    // Asha with no PIN typed.
    const { result } = renderHook(() => useAtTheCounter());
    act(() => arriveAtCounter(ASHA, IDLE_MINUTES, "server"));

    act(() => saveBlocked());
    expect(result.current).toBeNull();
    act(() => saveDevice(DAWA_LAPTOP));
    expect(result.current).toBeNull();
  });

  it("goes when the laptop is forgotten, or paired again as another device", () => {
    const { result } = renderHook(() => useAtTheCounter());
    act(() => arriveAtCounter(ASHA, IDLE_MINUTES, "server"));
    act(() =>
      saveDevice({
        ...DAWA_LAPTOP,
        id: "019a5e00-0000-7000-8000-000000000002",
      }),
    );
    expect(result.current).toBeNull();

    act(() => {
      saveDevice(DAWA_LAPTOP);
      arriveAtCounter(ASHA, IDLE_MINUTES, "server");
    });
    act(() => saveDevice(null));
    expect(result.current).toBeNull();
  });

  it("stays when the device check saves the laptop again, renamed", () => {
    // The check runs every few minutes, online: it must never send away the person at work.
    const { result } = renderHook(() => useAtTheCounter());
    act(() => arriveAtCounter(ASHA, IDLE_MINUTES, "server"));

    act(() => saveDevice({ ...DAWA_LAPTOP, name: "Laptop ya Dawa" }));

    expect(result.current?.staffId).toBe(ASHA.id);
  });
});

describe("a counter screen saying the person is leaving", () => {
  it("hides the person at once, and names who is leaving until the home page has heard", () => {
    // Toka on a counter screen. The screen can't end her session itself: that calls the server
    // (rule 5). It says so here, and the home page, which may call the server, does the logout.
    const note = renderHook(() => useAtTheCounter());
    const asked = renderHook(() => useLeaveAsked());
    act(() => arriveAtCounter(ASHA, IDLE_MINUTES, "server"));
    expect(asked.result.current).toBeNull();

    act(() => askToLeave());
    // Hidden at the press, as on the home page (UI-4): the next person must not see her meanwhile.
    expect(note.result.current).toBeNull();
    expect(asked.result.current?.staffId).toBe(ASHA.id);

    act(() => leaveHeard());
    expect(asked.result.current).toBeNull();
  });

  it("asks nothing while nobody is here", () => {
    const asked = renderHook(() => useLeaveAsked());

    act(() => askToLeave());

    expect(asked.result.current).toBeNull();
  });
});
