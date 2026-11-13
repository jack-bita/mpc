// busy.test.tsx — a counter screen in the middle of work marks itself busy, and the counter is quiet only
// once no screen in any tab is busy (SYNC-13, 03 §6.8).
//
// Two browsers are played: jsdom as it is, with no Web Locks, where only this tab's screens count; and
// jsdom with the stand-in locks (src/test/locks.ts), where another tab's busy screen counts too.
import { act, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { installFakeLocks, removeFakeLocks } from "@/test/locks";

import {
  BUSY_LOCK,
  counterIsQuiet,
  QUIET_CHECK_EVERY,
  useCounterBusy,
  useCounterQuiet,
} from "./busy";

/** A counter screen that is busy while `busy` is true: a sale with items in it, say. */
function Screen({ busy }: { busy: boolean }) {
  useCounterBusy(busy);
  return null;
}

/** Shows what useCounterQuiet says, as the update bar reads it. */
function Watcher({ watching }: { watching: boolean }) {
  return <p>{useCounterQuiet(watching) ? "quiet" : "busy"}</p>;
}

afterEach(() => {
  removeFakeLocks();
  vi.useRealTimers();
});

describe("counterIsQuiet in this tab", () => {
  it("is quiet with no screen busy", async () => {
    expect(await counterIsQuiet()).toBe(true);
  });

  it("is busy while a screen is busy, and quiet again once it is done", async () => {
    const view = render(<Screen busy />);
    expect(await counterIsQuiet()).toBe(false);

    view.rerender(<Screen busy={false} />);
    expect(await counterIsQuiet()).toBe(true);
  });

  it("stays busy while a second screen is still busy", async () => {
    // Two parts of one page, each with work open: the first one done is not the counter done.
    const view = render(
      <>
        <Screen busy />
        <Screen busy />
      </>,
    );
    view.rerender(
      <>
        <Screen busy={false} />
        <Screen busy />
      </>,
    );
    expect(await counterIsQuiet()).toBe(false);
  });

  it("is quiet again when a busy screen leaves the page", async () => {
    // A screen closed in the middle of its work, Toka say, ends its busy mark with it.
    const view = render(<Screen busy />);
    view.unmount();
    expect(await counterIsQuiet()).toBe(true);
  });
});

describe("counterIsQuiet across tabs", () => {
  it("is busy while another tab's screen is busy", async () => {
    const locks = installFakeLocks();
    const other = locks.holdInAnotherTab(BUSY_LOCK, "shared");
    await other.granted;
    expect(await counterIsQuiet()).toBe(false);

    // That tab's sale is done, or the tab was closed: the browser lets its lock go either way.
    other.release();
    await vi.waitFor(async () => expect(await counterIsQuiet()).toBe(true));
  });

  it("holds the shared lock while this tab's screen is busy, so other tabs see it", async () => {
    const locks = installFakeLocks();
    const view = render(<Screen busy />);
    await vi.waitFor(async () =>
      expect((await locks.query()).held).toEqual([
        { name: BUSY_LOCK, mode: "shared" },
      ]),
    );

    view.rerender(<Screen busy={false} />);
    await vi.waitFor(async () =>
      expect((await locks.query()).held).toEqual([]),
    );
  });

  it("counts a look the browser fails to answer as busy, and logs it", async () => {
    // Never guess quiet: an update can wait, a sale lost to a reload can't come back.
    const locks = installFakeLocks();
    vi.spyOn(locks, "query").mockRejectedValue(new Error("lock manager gone"));
    const log = vi.spyOn(console, "error").mockImplementation(() => {});

    expect(await counterIsQuiet()).toBe(false);
    expect(log).toHaveBeenCalledOnce();
  });

  it("never counts the sync's lock as busy", async () => {
    // The sync runs beside every screen all day (lock.ts): it must not keep an update away.
    const locks = installFakeLocks();
    const sync = locks.holdInAnotherTab("mpc-sync-shop");
    await sync.granted;
    expect(await counterIsQuiet()).toBe(true);
    sync.release();
  });
});

describe("useCounterQuiet", () => {
  it("says busy while it isn't watching, whatever the counter is", () => {
    // Nothing to wait for, no update waiting: it asks nothing, and the bar stays hidden.
    const view = render(<Watcher watching={false} />);
    expect(view.container.textContent).toBe("busy");
  });

  it("says quiet once it has looked, and busy as soon as this tab's screen is busy", async () => {
    const view = render(
      <>
        <Screen busy={false} />
        <Watcher watching />
      </>,
    );
    await vi.waitFor(() => expect(view.container.textContent).toBe("quiet"));

    // This tab's own screen: heard at once, with no wait for the next look.
    view.rerender(
      <>
        <Screen busy />
        <Watcher watching />
      </>,
    );
    await vi.waitFor(() => expect(view.container.textContent).toBe("busy"));

    view.rerender(
      <>
        <Screen busy={false} />
        <Watcher watching />
      </>,
    );
    await vi.waitFor(() => expect(view.container.textContent).toBe("quiet"));
  });

  it("sees another tab's screen end at its next look", async () => {
    // Another tab tells this one nothing when its sale ends, or when it is closed mid-sale: this tab
    // looks again every QUIET_CHECK_EVERY while it watches.
    vi.useFakeTimers();
    const locks = installFakeLocks();
    const other = locks.holdInAnotherTab(BUSY_LOCK, "shared");
    const view = render(<Watcher watching />);
    await act(() => vi.advanceTimersByTimeAsync(0));
    expect(view.container.textContent).toBe("busy");

    other.release();
    await act(() => vi.advanceTimersByTimeAsync(QUIET_CHECK_EVERY));
    expect(view.container.textContent).toBe("quiet");
  });

  it("stops looking once it no longer watches", async () => {
    vi.useFakeTimers();
    const locks = installFakeLocks();
    const query = vi.spyOn(locks, "query");
    const view = render(<Watcher watching />);
    await act(() => vi.advanceTimersByTimeAsync(0));

    view.rerender(<Watcher watching={false} />);
    const asked = query.mock.calls.length;
    await act(() => vi.advanceTimersByTimeAsync(QUIET_CHECK_EVERY * 3));
    expect(query.mock.calls.length).toBe(asked);
  });
});
