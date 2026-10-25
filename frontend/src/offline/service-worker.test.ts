// service-worker.test.ts — the page registers the service worker only where one exists (SPIKE-1).
//
// jsdom, the fake browser, has no service workers at all, so each test gives `navigator` a fake one,
// or leaves it without. Whether the real browser installs the worker is checked on the devices.
import { afterEach, describe, expect, it, vi } from "vitest";

import { registerServiceWorker } from "./service-worker";

/** A fake navigator.serviceWorker whose register() succeeds; returns it to check the calls. */
function fakeServiceWorkers() {
  const register = vi.fn().mockResolvedValue({});
  Object.defineProperty(navigator, "serviceWorker", {
    value: { register },
    configurable: true,
  });
  return register;
}

afterEach(() => {
  vi.unstubAllEnvs();
  // Remove the fake, so each test starts from jsdom's navigator again.
  Reflect.deleteProperty(navigator, "serviceWorker");
});

describe("registerServiceWorker", () => {
  it("registers /sw.js for the whole app in the built app", () => {
    vi.stubEnv("NODE_ENV", "production");
    const register = fakeServiceWorkers();

    registerServiceWorker();

    expect(register).toHaveBeenCalledWith("/sw.js", { scope: "/" });
  });

  it("does nothing in development, where no sw.js exists", () => {
    vi.stubEnv("NODE_ENV", "development");
    const register = fakeServiceWorkers();

    registerServiceWorker();

    expect(register).not.toHaveBeenCalled();
  });

  it("does nothing in a browser without service workers", () => {
    vi.stubEnv("NODE_ENV", "production");
    expect("serviceWorker" in navigator).toBe(false);

    expect(() => registerServiceWorker()).not.toThrow();
  });
});
