// idle-lock.test.tsx — a shared laptop locks itself when nobody has touched it for the shop's idle minutes
// (UI-4, 03 §5.9). The clock is a fake one, so 15 minutes pass in a moment: vi.useFakeTimers moves
// setInterval and Date.now() together.
import { fireEvent, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { IDLE_CHECK_EVERY, useIdleLock } from "./idle-lock";

const MINUTE = 60 * 1000;

/** A screen in miniature that keeps the lock, as the home page does. */
function Locked(props: { minutes: number | null; onIdle: () => void }) {
  useIdleLock(props.minutes, props.onIdle);
  return null;
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("the idle lock", () => {
  it("locks once nobody has touched the laptop for the idle minutes", () => {
    const idle = vi.fn();
    render(<Locked minutes={15} onIdle={idle} />);

    vi.advanceTimersByTime(15 * MINUTE - IDLE_CHECK_EVERY);
    expect(idle).not.toHaveBeenCalled();

    // Found at the next check: at most a few seconds late.
    vi.advanceTimersByTime(IDLE_CHECK_EVERY);
    expect(idle).toHaveBeenCalledOnce();
  });

  it("starts the wait again at each tap and each key press", () => {
    const idle = vi.fn();
    render(<Locked minutes={15} onIdle={idle} />);

    vi.advanceTimersByTime(14 * MINUTE);
    fireEvent.pointerDown(window);
    vi.advanceTimersByTime(14 * MINUTE);
    fireEvent.keyDown(window, { key: "5" });
    vi.advanceTimersByTime(14 * MINUTE);
    expect(idle).not.toHaveBeenCalled();

    vi.advanceTimersByTime(MINUTE + IDLE_CHECK_EVERY);
    expect(idle).toHaveBeenCalledOnce();
  });

  it("locks as soon as a laptop that slept is opened again", () => {
    // A lid closed for two hours: the browser's timers sleep too, so a timer alone would wait out its
    // last minutes after the lid opens, with the person still on the screen. The clock doesn't sleep.
    const idle = vi.fn();
    render(<Locked minutes={15} onIdle={idle} />);

    vi.setSystemTime(Date.now() + 2 * 60 * MINUTE);
    document.dispatchEvent(new Event("visibilitychange"));

    expect(idle).toHaveBeenCalledOnce();
  });

  it("locks once, not again at every check that follows", () => {
    // The logout it starts takes a moment; meanwhile nothing should send a second one.
    const idle = vi.fn();
    render(<Locked minutes={15} onIdle={idle} />);

    vi.advanceTimersByTime(30 * MINUTE);

    expect(idle).toHaveBeenCalledOnce();
  });

  it("never locks without idle minutes: nobody is here", () => {
    const idle = vi.fn();
    render(<Locked minutes={null} onIdle={idle} />);

    vi.advanceTimersByTime(24 * 60 * MINUTE);
    fireEvent(document, new Event("visibilitychange"));

    expect(idle).not.toHaveBeenCalled();
  });

  it("stops watching once the screen has gone", () => {
    const idle = vi.fn();
    const { unmount } = render(<Locked minutes={15} onIdle={idle} />);

    unmount();
    vi.advanceTimersByTime(30 * MINUTE);

    expect(idle).not.toHaveBeenCalled();
  });
});
