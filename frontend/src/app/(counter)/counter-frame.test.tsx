// counter-frame.test.tsx — the frame around every counter screen (SYNC-11, 03 §7.1): the person at the
// counter in the bar, with the side they work on, their own language and font, Badilisha mtu and Toka, and
// the idle lock; nobody, back to the name tiles. It reads only the laptop: the counter's note of who is
// here (at-the-counter.ts) and their row on the laptop's copy, and never calls the server.
import {
  act,
  fireEvent,
  renderHook,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { saveDevice } from "@/features/devices/this-device";
import {
  arriveAtCounter,
  useLeaveAsked,
} from "@/features/login/at-the-counter";
import { shopDatabase } from "@/offline/this-shop";
import { DAWA, DAWA_LAPTOP } from "@/test/devices";
import { swahiliIn } from "@/test/language";
import { staffRow, theLaptopKnows } from "@/test/laptop";
import { render } from "@/test/render";
import { router } from "@/test/router";
import { DAWA_SIDE } from "@/test/shop-lists";

import CounterLayout from "./layout";

// Asha, a seller on Dawa, as the sync left her on the laptop. A fake person.
const ASHA = {
  ...staffRow("019a5e00-0000-7000-8000-0000000000c2", "Asha Mfano", "Asha"),
  permissions: {
    every_side: [],
    sides: [{ side: DAWA.id, permissions: ["sale.make"] }],
  },
};

/** The shop's idle minutes, as the home page hands them to the counter with her. */
const IDLE_MINUTES = 15;

const db = () => shopDatabase(DAWA_LAPTOP.shop.id);
const bar = () => within(screen.getByRole("banner"));
const leaveAsked = () => renderHook(() => useLeaveAsked()).result.current;

// The Dawa laptop, registered, with Asha and the Dawa side on its copy.
beforeEach(async () => {
  saveDevice(DAWA_LAPTOP);
  await theLaptopKnows(ASHA);
  await db().side.put(DAWA_SIDE);
});

/** A counter screen, with Asha logged in at the home page before it opened. */
async function ashaAtTheCounter() {
  arriveAtCounter(ASHA, IDLE_MINUTES);
  render(
    <CounterLayout>
      <p>screen</p>
    </CounterLayout>,
  );
  await screen.findByText("screen");
}

describe("the counter's frame", () => {
  it("puts the screen under the bar, naming her and the side she works on", async () => {
    await ashaAtTheCounter();

    expect(bar().getByText("Asha")).toBeDefined();
    expect(bar().getByText("MPC · Dawa")).toBeDefined();
    expect(screen.getByRole("main").textContent).toBe("screen");
    // Hers is in Mipangilio yangu: the bar's language button is the laptop's own (UI-9).
    expect(bar().queryByRole("button", { name: "English" })).toBeNull();
  });

  it("sends nobody back to the name tiles, and shows them no screen", async () => {
    // A reload ends the note, as it ends a local session (Jack, SYNC-10): the PIN again, at the home page.
    render(
      <CounterLayout>
        <p>screen</p>
      </CounterLayout>,
    );

    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/"));
    expect(screen.queryByText("screen")).toBeNull();
  });

  it("waits while her row is read, and sends her nowhere meanwhile", () => {
    // The first drawing knows the note but not yet her row: still reading is not nobody.
    arriveAtCounter(ASHA, IDLE_MINUTES);
    render(
      <CounterLayout>
        <p>screen</p>
      </CounterLayout>,
    );

    expect(screen.queryByText("screen")).toBeNull();
    expect(router.replace).not.toHaveBeenCalled();
  });

  it("Toka hides her at once, and asks the home page to log her out", async () => {
    await ashaAtTheCounter();

    fireEvent.click(bar().getByRole("button", { name: "Toka" }));

    // A counter screen can't log her out itself: that calls the server (rule 5). The home page does.
    expect(leaveAsked()).toBe(ASHA.id);
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/"));
    expect(screen.queryByText("screen")).toBeNull();
    expect(bar().queryByText("Asha")).toBeNull();
  });

  it("Badilisha mtu does the same, for the next person stepping up", async () => {
    await ashaAtTheCounter();

    fireEvent.click(bar().getByRole("button", { name: "Badilisha mtu" }));

    expect(leaveAsked()).toBe(ASHA.id);
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/"));
  });

  it("sends her back once a sync says she is suspended", async () => {
    // X2: suspended at 10:00 in the office; the next pull brings it to the laptop.
    await ashaAtTheCounter();

    await act(() => db().staff.put({ ...ASHA, status: "suspended" }));

    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/"));
    expect(screen.queryByText("screen")).toBeNull();
  });

  it("shows her in her own language and font, from her row on the laptop", async () => {
    await db().staff.put({ ...ASHA, language: "en", font: "second" });
    await ashaAtTheCounter();

    expect(bar().getByRole("button", { name: "Log out" })).toBeDefined();
    expect(swahiliIn(screen.getByRole("banner"))).toEqual([]);
    expect(document.documentElement.dataset.font).toBe("second");
  });
});

describe("the counter's idle lock", () => {
  // The fake clock moves its timers and the time only, and still runs on its own: the test database
  // (fake-indexeddb) runs on setImmediate, which must stay real, or its reads never end (SYNC-10).
  beforeEach(() => {
    vi.useFakeTimers({
      shouldAdvanceTime: true,
      toFake: [
        "setTimeout",
        "setInterval",
        "clearTimeout",
        "clearInterval",
        "Date",
      ],
    });
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("logs her out after the shop's idle minutes untouched, as the home page would", async () => {
    // She clocks in, and walks away from the counter with the screen open in her name.
    await ashaAtTheCounter();

    await act(() =>
      vi.advanceTimersByTimeAsync(IDLE_MINUTES * 60 * 1000 + 10 * 1000),
    );

    expect(leaveAsked()).toBe(ASHA.id);
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/"));
  });

  it("keeps her while she works", async () => {
    await ashaAtTheCounter();

    await act(() => vi.advanceTimersByTimeAsync(10 * 60 * 1000));
    fireEvent.pointerDown(window);
    await act(() => vi.advanceTimersByTimeAsync(10 * 60 * 1000));

    expect(leaveAsked()).toBeNull();
    expect(screen.getByText("screen")).toBeDefined();
  });
});
