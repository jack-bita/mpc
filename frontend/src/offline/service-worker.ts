// service-worker.ts — registers the service worker (src/sw.ts, built into out/sw.js) from the page, and
// says when a new version is waiting (SPIKE-1, 03 §6.8, §7.7).
//
// Registering asks the browser to install /sw.js and keep it for this site. From then on the browser
// checks /sw.js for a new version by itself: whenever the app opens with internet, and about once a day.
// A new version downloads in the background, then waits (sw.ts: skipWaiting false) until someone taps
// Toleo jipya: the app must never reload in the middle of a sale (03 §6.7).

/** Switches to the waiting version: the new worker takes over, then the page reloads from it. */
export type ApplyUpdate = () => void;

/**
 * Asks the browser to install the service worker, and calls `onUpdateReady` when a new version waits.
 * Safe on every page load: the browser installs the same sw.js only once.
 * `reload` is replaced only by tests, because jsdom can't reload a page.
 */
export async function registerServiceWorker(
  onUpdateReady: (apply: ApplyUpdate) => void,
  reload: () => void = () => window.location.reload(),
): Promise<void> {
  // Only the built app has a service worker: `serwist build` runs after `next build`, and `next dev`
  // serves no /sw.js. Next.js writes the value of NODE_ENV into the code at build time.
  if (process.env.NODE_ENV !== "production") return;
  // Chrome and Edge, the shop's browsers (03 §7.3), have service workers, but an old or locked-down
  // browser may not. The app then still works online, only not offline.
  if (!("serviceWorker" in navigator)) return;

  // scope "/": the worker looks after every page of the app. A failed registration (no internet on the
  // very first visit, say) is only logged: the browser tries again on the next page load.
  let registration: ServiceWorkerRegistration;
  try {
    registration = await navigator.serviceWorker.register("/sw.js", {
      scope: "/",
    });
  } catch (error) {
    console.error("service worker registration failed", error);
    return;
  }

  // An update is something to offer only when a version already runs this page. On the very first
  // install there is nothing to replace: the new worker takes charge by itself (sw.ts: clientsClaim).
  const offer = (worker: ServiceWorker) => {
    if (!navigator.serviceWorker.controller) return;
    onUpdateReady(() => {
      // Past "installed", the new version is taking over or has taken over already: another tab
      // switched first. The browser announced it (controllerchange) as the version began taking over,
      // so waiting for that announcement now would wait forever. Only this page is old: reload it.
      if (worker.state !== "installed") {
        reload();
        return;
      }
      // Reload only once the new version has taken over, so the reloaded page comes from it.
      // once: the listener removes itself, so a later switch can't reload this page again.
      navigator.serviceWorker.addEventListener(
        "controllerchange",
        () => reload(),
        { once: true },
      );
      // sw.ts listens for this message and stops waiting.
      worker.postMessage({ type: "SKIP_WAITING" });
    });
  };

  // A version that finished downloading on an earlier visit and still waits: offer it at once.
  if (registration.waiting) offer(registration.waiting);

  // A version that starts downloading from now on: offer it once it has fully installed, never
  // half-way, when some of its files may still be missing.
  registration.addEventListener("updatefound", () => {
    const worker = registration.installing;
    if (!worker) return;
    worker.addEventListener("statechange", () => {
      if (worker.state === "installed") offer(worker);
    });
  });
}
