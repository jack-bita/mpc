// service-worker.test.ts — the page registers the service worker only where one exists, offers a new
// version only when one is ready to take over, and looks for one regularly (SPIKE-1, SYNC-13, 03 §6.8).
//
// jsdom, the fake browser, has no service workers, so these tests build small fakes on EventTarget, the
// browser's own way of sending events. Whether a real browser installs and switches is checked on the
// shop's devices.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { registerServiceWorker, UPDATE_CHECK_EVERY } from "./service-worker";
import { tellAppTooOld } from "./sync/too-old";

/** A fake worker: it has a state, and records the messages the page sends it. */
class FakeWorker extends EventTarget {
  state: ServiceWorkerState = "installing";
  postMessage = vi.fn();

  /** Moves to a new state and tells the listeners, as the browser does. */
  become(state: ServiceWorkerState) {
    this.state = state;
    this.dispatchEvent(new Event("statechange"));
  }
}

/** A fake registration: the browser's record of this site's worker, and of any newer one. */
class FakeRegistration extends EventTarget {
  installing: FakeWorker | null = null;
  waiting: FakeWorker | null = null;
  // The page asking the browser to look for a new version now (SYNC-13): found nothing, unless a test says.
  update = vi.fn(() => Promise.resolve());

  /** A new version starts downloading, as after a deploy. */
  findUpdate(): FakeWorker {
    const worker = new FakeWorker();
    this.installing = worker;
    this.dispatchEvent(new Event("updatefound"));
    return worker;
  }
}

/** Gives navigator a fake serviceWorker. `controlled`: a version already runs this page. */
function fakeServiceWorkers({
  controlled = true,
  registration = new FakeRegistration(),
} = {}) {
  const container = Object.assign(new EventTarget(), {
    controller: controlled ? new FakeWorker() : null,
    register: vi.fn().mockResolvedValue(registration),
  });
  Object.defineProperty(navigator, "serviceWorker", {
    value: container,
    configurable: true,
  });
  return { container, registration };
}

beforeEach(() => {
  vi.stubEnv("NODE_ENV", "production");
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.useRealTimers();
  vi.restoreAllMocks();
  // Remove the fake, so each test starts from jsdom's navigator again.
  Reflect.deleteProperty(navigator, "serviceWorker");
});

describe("registerServiceWorker", () => {
  it("registers /sw.js for the whole app in the built app", async () => {
    const { container } = fakeServiceWorkers();

    await registerServiceWorker(vi.fn());

    expect(container.register).toHaveBeenCalledWith("/sw.js", { scope: "/" });
  });

  it("does nothing in development, where no sw.js exists", async () => {
    vi.stubEnv("NODE_ENV", "development");
    const { container } = fakeServiceWorkers();

    await registerServiceWorker(vi.fn());

    expect(container.register).not.toHaveBeenCalled();
  });

  it("does nothing in a browser without service workers", async () => {
    expect("serviceWorker" in navigator).toBe(false);

    // Hands back a stop that has nothing to stop.
    const stop = await registerServiceWorker(vi.fn());
    expect(() => stop()).not.toThrow();
  });

  it("offers a new version once it has fully installed", async () => {
    const { registration } = fakeServiceWorkers();
    const onUpdateReady = vi.fn();
    await registerServiceWorker(onUpdateReady);

    const worker = registration.findUpdate();
    // Still downloading: some of its files may be missing.
    expect(onUpdateReady).not.toHaveBeenCalled();

    worker.become("installed");
    expect(onUpdateReady).toHaveBeenCalledOnce();
  });

  it("offers nothing on the very first install", async () => {
    const { registration } = fakeServiceWorkers({ controlled: false });
    const onUpdateReady = vi.fn();
    await registerServiceWorker(onUpdateReady);

    registration.findUpdate().become("installed");

    expect(onUpdateReady).not.toHaveBeenCalled();
  });

  it("offers at once a version still waiting from an earlier visit", async () => {
    const registration = new FakeRegistration();
    registration.waiting = new FakeWorker();
    registration.waiting.state = "installed";
    fakeServiceWorkers({ registration });
    const onUpdateReady = vi.fn();

    await registerServiceWorker(onUpdateReady);

    expect(onUpdateReady).toHaveBeenCalledOnce();
  });

  it("on apply, tells the new version to stop waiting, and offers the reload once it has taken over", async () => {
    const { container, registration } = fakeServiceWorkers();
    const reload = vi.fn();
    const onUpdateReady = vi.fn();
    await registerServiceWorker(onUpdateReady, reload);
    const worker = registration.findUpdate();
    worker.become("installed");
    const apply = onUpdateReady.mock.calls[0]![0] as () => void;

    apply();
    expect(worker.postMessage).toHaveBeenCalledWith({ type: "SKIP_WAITING" });
    // A reload now would load the old version again: the new one hasn't taken over yet.
    expect(reload).not.toHaveBeenCalled();

    // Taken over: offered as to any other tab, never a reload on the spot. The new version can take a while
    // to take over, and a sale started meanwhile must finish first (update-prompt.tsx waits for it).
    container.controller = new FakeWorker();
    container.dispatchEvent(new Event("controllerchange"));
    expect(reload).not.toHaveBeenCalled();
    expect(onUpdateReady).toHaveBeenCalledTimes(2);
    expect(onUpdateReady.mock.calls[1]![1]).toBe("taken_over");
    (onUpdateReady.mock.calls[1]![0] as () => void)();
    expect(reload).toHaveBeenCalledOnce();
  });

  // "activating" matters most: the browser announces the new version (controllerchange) as it starts
  // taking over, so a tab that waited for the announcement from then on would wait forever.
  it.each(["activating", "activated"] as const)(
    "on apply, reloads at once when another tab has switched already (%s)",
    async (state) => {
      const { registration } = fakeServiceWorkers();
      const reload = vi.fn();
      const onUpdateReady = vi.fn();
      await registerServiceWorker(onUpdateReady, reload);
      const worker = registration.findUpdate();
      worker.become("installed");
      const apply = onUpdateReady.mock.calls[0]![0] as () => void;

      worker.become(state);
      apply();

      expect(reload).toHaveBeenCalledOnce();
      expect(worker.postMessage).not.toHaveBeenCalled();
    },
  );

  it("offers nothing when a version waits but none runs this page", async () => {
    // After a hard reload (Shift+F5) the browser runs the page with no service worker at all.
    const registration = new FakeRegistration();
    registration.waiting = new FakeWorker();
    registration.waiting.state = "installed";
    fakeServiceWorkers({ controlled: false, registration });
    const onUpdateReady = vi.fn();

    await registerServiceWorker(onUpdateReady);

    expect(onUpdateReady).not.toHaveBeenCalled();
  });

  it("logs a failed registration and carries on", async () => {
    const { container } = fakeServiceWorkers();
    container.register.mockRejectedValue(new TypeError("bad script type"));
    // Silence the expected log line, and check it was written.
    const log = vi.spyOn(console, "error").mockImplementation(() => {});

    const stop = await registerServiceWorker(vi.fn());

    expect(log).toHaveBeenCalledOnce();
    expect(() => stop()).not.toThrow();
    log.mockRestore();
  });
});

describe("the regular looks for a new version", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  it("a counter left open all day still gets the bar after a deploy, with no reload", async () => {
    // The Dawa laptop opened the app at 07:00 and never reloaded it. A deploy lands at 09:30.
    const { registration } = fakeServiceWorkers();
    registration.update.mockImplementation(() => {
      registration.findUpdate().become("installed");
      return Promise.resolve();
    });
    const reload = vi.fn();
    const onUpdateReady = vi.fn();
    await registerServiceWorker(onUpdateReady, reload);

    await vi.advanceTimersByTimeAsync(UPDATE_CHECK_EVERY);

    expect(onUpdateReady).toHaveBeenCalledOnce();
    expect(reload).not.toHaveBeenCalled();
  });

  it("looks every hour, and not before", async () => {
    const { registration } = fakeServiceWorkers();
    await registerServiceWorker(vi.fn());

    await vi.advanceTimersByTimeAsync(UPDATE_CHECK_EVERY - 1);
    expect(registration.update).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1);
    expect(registration.update).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(UPDATE_CHECK_EVERY);
    expect(registration.update).toHaveBeenCalledTimes(2);
  });

  it("looks as soon as the network comes back", async () => {
    // Offline at the hour, the laptop would otherwise wait for the next one.
    const { registration } = fakeServiceWorkers();
    await registerServiceWorker(vi.fn());

    window.dispatchEvent(new Event("online"));

    expect(registration.update).toHaveBeenCalledOnce();
  });

  it("doesn't look while the browser says there is no network", async () => {
    const { registration } = fakeServiceWorkers();
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    await registerServiceWorker(vi.fn());

    await vi.advanceTimersByTimeAsync(UPDATE_CHECK_EVERY);

    expect(registration.update).not.toHaveBeenCalled();
  });

  it("passes over a look that fails, quietly, and looks again at the next hour", async () => {
    // A router whose mobile data is down: sw.js can't be fetched.
    const { registration } = fakeServiceWorkers();
    // A plain function, not a vi.fn: a vi.fn watches the promises it hands back, and its watching would
    // count as catching the failure, so a look that never caught it would still pass here.
    let looks = 0;
    Object.defineProperty(registration, "update", {
      value: () => {
        looks += 1;
        return Promise.reject(new TypeError("Failed to fetch"));
      },
    });
    const log = vi.spyOn(console, "error");
    // A failure nobody caught: Node tells this listener once the work at hand is done. Vitest alone
    // doesn't fail this test for it, so the test listens itself.
    const uncaught = vi.fn();
    process.on("unhandledRejection", uncaught);
    await registerServiceWorker(vi.fn());

    await vi.advanceTimersByTimeAsync(UPDATE_CHECK_EVERY * 2);
    // A real turn of the clock, so Node has had its chance to tell.
    vi.useRealTimers();
    await new Promise((resolve) => setTimeout(resolve, 0));
    process.off("unhandledRejection", uncaught);

    expect(looks).toBe(2);
    expect(log).not.toHaveBeenCalled();
    expect(uncaught).not.toHaveBeenCalled();
  });

  it("looks at once when a sync finds the app too old", async () => {
    // The pulls have stopped: the new version can't wait for the hour.
    const { registration } = fakeServiceWorkers();
    await registerServiceWorker(vi.fn());

    tellAppTooOld();

    expect(registration.update).toHaveBeenCalledOnce();
  });

  it("stops looking once stopped", async () => {
    const { registration } = fakeServiceWorkers();
    const stop = await registerServiceWorker(vi.fn());

    stop();
    await vi.advanceTimersByTimeAsync(UPDATE_CHECK_EVERY * 2);
    window.dispatchEvent(new Event("online"));
    tellAppTooOld();

    expect(registration.update).not.toHaveBeenCalled();
  });
});

describe("a switch another tab made", () => {
  /** Another tab tapped Sasisha: the new version takes over this page too, as the browser does. */
  function anotherTabSwitched(
    container: EventTarget & { controller: unknown },
  ) {
    container.controller = new FakeWorker();
    container.dispatchEvent(new Event("controllerchange"));
  }

  it("offers this old tab a reload, marked as taken over", async () => {
    // The Dawa laptop has two tabs open, and Asha switched in the other one. This tab still runs the
    // old code, served by a worker that has deleted the old version's files (SPIKE-1).
    const { container } = fakeServiceWorkers();
    const reload = vi.fn();
    const onUpdateReady = vi.fn();
    await registerServiceWorker(onUpdateReady, reload);

    anotherTabSwitched(container);

    expect(onUpdateReady).toHaveBeenCalledOnce();
    expect(onUpdateReady.mock.calls[0]![1]).toBe("taken_over");
    // The reload waits for the bar, which waits for a quiet counter (update-prompt.tsx).
    expect(reload).not.toHaveBeenCalled();
    (onUpdateReady.mock.calls[0]![0] as () => void)();
    expect(reload).toHaveBeenCalledOnce();
  });

  it("offers nothing when the very first version takes charge", async () => {
    // A laptop's first visit: no version ran this page, so nothing old is left in it (sw.ts: clientsClaim).
    const { container } = fakeServiceWorkers({ controlled: false });
    const onUpdateReady = vi.fn();
    await registerServiceWorker(onUpdateReady);

    anotherTabSwitched(container);

    expect(onUpdateReady).not.toHaveBeenCalled();
  });

  it("offers a later switch to a page the first version took charge of", async () => {
    // That page stayed open all day: by the next deploy a version runs it, and the switch is a switch.
    const { container } = fakeServiceWorkers({ controlled: false });
    const onUpdateReady = vi.fn();
    await registerServiceWorker(onUpdateReady);
    anotherTabSwitched(container);

    anotherTabSwitched(container);

    expect(onUpdateReady).toHaveBeenCalledOnce();
    expect(onUpdateReady.mock.calls[0]![1]).toBe("taken_over");
  });

  it("offers the tab that switched itself the reload once, as taken over", async () => {
    // Asha tapped Sasisha here. The new version can take a while to take over (it waits for the old one's
    // last work, a background push say), and Juma may start a sale in this tab meanwhile: this tab waits
    // for a quiet counter like every other.
    const { container, registration } = fakeServiceWorkers();
    const reload = vi.fn();
    const onUpdateReady = vi.fn();
    await registerServiceWorker(onUpdateReady, reload);
    registration.findUpdate().become("installed");
    expect(onUpdateReady.mock.calls[0]![1]).toBe("waiting");

    (onUpdateReady.mock.calls[0]![0] as () => void)();
    anotherTabSwitched(container);

    expect(reload).not.toHaveBeenCalled();
    expect(onUpdateReady).toHaveBeenCalledTimes(2);
    expect(onUpdateReady.mock.calls[1]![1]).toBe("taken_over");
  });

  it("stops listening once stopped", async () => {
    const { container } = fakeServiceWorkers();
    const onUpdateReady = vi.fn();
    const stop = await registerServiceWorker(onUpdateReady);

    stop();
    anotherTabSwitched(container);

    expect(onUpdateReady).not.toHaveBeenCalled();
  });
});
