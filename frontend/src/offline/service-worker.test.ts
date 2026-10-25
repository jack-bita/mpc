// service-worker.test.ts — the page registers the service worker only where one exists, and offers a
// new version only when one is ready to take over (SPIKE-1, 03 §6.8).
//
// jsdom, the fake browser, has no service workers, so these tests build small fakes on EventTarget, the
// browser's own way of sending events. Whether a real browser installs and switches is checked on the
// shop's devices.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { registerServiceWorker } from "./service-worker";

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

    await expect(registerServiceWorker(vi.fn())).resolves.toBeUndefined();
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

  it("on apply, tells the new version to stop waiting, and reloads only once it has taken over", async () => {
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

    container.dispatchEvent(new Event("controllerchange"));
    expect(reload).toHaveBeenCalledOnce();
  });

  it("on apply, reloads at once when another tab has switched already", async () => {
    const { registration } = fakeServiceWorkers();
    const reload = vi.fn();
    const onUpdateReady = vi.fn();
    await registerServiceWorker(onUpdateReady, reload);
    const worker = registration.findUpdate();
    worker.become("installed");
    const apply = onUpdateReady.mock.calls[0]![0] as () => void;

    worker.become("activated");
    apply();

    expect(reload).toHaveBeenCalledOnce();
    expect(worker.postMessage).not.toHaveBeenCalled();
  });
});
