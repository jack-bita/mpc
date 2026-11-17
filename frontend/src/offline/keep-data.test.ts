// keep-data.test.ts — the browser's two answers on keeping the shop's data (SYNC-12): persistent storage,
// and the install. The browser is a stand-in here: jsdom has neither question.
import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  askToKeepData,
  forgetKeepData,
  install,
  type InstallPromptEvent,
  useKeepData,
  watchInstall,
} from "./keep-data";

afterEach(() => {
  forgetKeepData();
  vi.unstubAllGlobals();
});

/** A browser's storage that answers `persisted` and `persist` as told. */
function storage(already: boolean, yes: boolean) {
  return {
    persisted: vi.fn(async () => already),
    persist: vi.fn(async () => yes),
  } as unknown as StorageManager;
}

describe("asking to keep the data", () => {
  it("is kept when the browser says yes", async () => {
    const browser = storage(false, true);
    expect(await askToKeepData(browser)).toBe("kept");
    expect(browser.persist).toHaveBeenCalledOnce();
  });

  it("doesn't ask again a browser that said yes before", async () => {
    const browser = storage(true, true);
    expect(await askToKeepData(browser)).toBe("kept");
    expect(browser.persist).not.toHaveBeenCalled();
  });

  it("is not kept when the browser says no, as Chrome does on localhost", async () => {
    expect(await askToKeepData(storage(false, false))).toBe("not_kept");
  });

  it("can't ask a browser with no such question", async () => {
    expect(await askToKeepData(undefined)).toBe("cannot_ask");
  });

  it("can't ask a browser that throws, as one that blocks storage does", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const browser = {
      persisted: vi.fn(async () => {
        throw new Error("blocked");
      }),
      persist: vi.fn(),
    } as unknown as StorageManager;
    expect(await askToKeepData(browser)).toBe("cannot_ask");
  });

  it("tells the page its answer", async () => {
    const { result } = renderHook(() => useKeepData());
    expect(result.current.kept).toBe("asking");
    await act(() => askToKeepData(storage(false, true)));
    expect(result.current.kept).toBe("kept");
  });
});

/** Chrome's install offer, as the browser fires it, with the manager's answer to its question. */
function offer(outcome: "accepted" | "dismissed"): InstallPromptEvent {
  const event = new Event("beforeinstallprompt", {
    cancelable: true,
  }) as InstallPromptEvent;
  event.prompt = vi.fn(async () => {});
  event.userChoice = Promise.resolve({ outcome });
  return event;
}

describe("the install", () => {
  it("shows the menu's steps when the browser offers nothing", () => {
    const stop = watchInstall();
    const { result } = renderHook(() => useKeepData());
    expect(result.current.install.kind).toBe("steps");
    stop();
  });

  it("keeps the browser's offer for the page's button, and keeps Chrome's own bar away", () => {
    const stop = watchInstall();
    const { result } = renderHook(() => useKeepData());
    const event = offer("accepted");
    act(() => {
      window.dispatchEvent(event);
    });
    expect(result.current.install).toEqual({ kind: "offered", offer: event });
    expect(event.defaultPrevented).toBe(true);
    stop();
  });

  it("says installed once the browser has installed it", () => {
    const stop = watchInstall();
    const { result } = renderHook(() => useKeepData());
    act(() => {
      window.dispatchEvent(new Event("appinstalled"));
    });
    expect(result.current.install.kind).toBe("installed");
    stop();
  });

  it("says installed when the page opens in the app's own window", () => {
    vi.stubGlobal(
      "matchMedia",
      vi.fn(() => ({ matches: true })),
    );
    const stop = watchInstall();
    const { result } = renderHook(() => useKeepData());
    expect(result.current.install.kind).toBe("installed");
    stop();
  });

  it("goes back to the menu's steps when the manager dismisses the question", async () => {
    const stop = watchInstall();
    const { result } = renderHook(() => useKeepData());
    const event = offer("dismissed");
    act(() => {
      window.dispatchEvent(event);
    });
    await act(() => install(event));
    expect(event.prompt).toHaveBeenCalledOnce();
    expect(result.current.install.kind).toBe("steps");
    stop();
  });
});
