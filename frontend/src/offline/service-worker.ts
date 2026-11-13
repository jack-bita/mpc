// service-worker.ts — registers the service worker (src/sw.ts, built into out/sw.js) from the page, says
// when a new version is waiting, and looks for one regularly (SPIKE-1, SYNC-13, 03 §6.8, §7.7).
//
// Registering asks the browser to install /sw.js and keep it for this site. From then on the browser
// checks /sw.js for a new version by itself each time a page of the app loads with internet. It sets
// no timer of its own: a counter left open all day would see a deploy only after a reload (SPIKE-1). So
// the page asks it to look every UPDATE_CHECK_EVERY, and when the network comes back (SYNC-13).
// A new version downloads in the background, then waits (sw.ts: skipWaiting false) until someone taps
// Sasisha on the Toleo jipya bar, or until every window of the app is closed: the app must never
// reload in the middle of a sale (03 §6.7).

/** Switches to the waiting version: the new worker takes over, then the page reloads from it. */
export type ApplyUpdate = () => void;

/** How often an open app asks the browser to look for a new version (03 §6.8, a default): a deploy
 * reaches a counter left open all day within the hour. Each look fetches only sw.js, a small file, and
 * downloads the rest only when it has changed. */
export const UPDATE_CHECK_EVERY = 60 * 60 * 1000;

/**
 * Asks the browser to install the service worker, calls `onUpdateReady` when a new version waits, and
 * looks for one every UPDATE_CHECK_EVERY and when the network comes back, until the function it hands
 * back is called. Safe on every page load: the browser installs the same sw.js only once.
 * `reload` is replaced only by tests, because jsdom can't reload a page.
 */
export async function registerServiceWorker(
  onUpdateReady: (apply: ApplyUpdate) => void,
  reload: () => void = () => window.location.reload(),
): Promise<() => void> {
  // Only the built app has a service worker: `serwist build` runs after `next build`, and `next dev`
  // serves no /sw.js. Next.js writes the value of NODE_ENV into the code at build time.
  if (process.env.NODE_ENV !== "production") return nothing;
  // Chrome and Edge, the shop's browsers (03 §7.3), have service workers, but an old or locked-down
  // browser may not. The app then still works online, only not offline.
  if (!("serviceWorker" in navigator)) return nothing;

  // scope "/": the worker looks after every page of the app. A failed registration (sw.js missing or
  // of the wrong type, the connection dropping, service workers switched off) is only logged: this
  // function runs again on the next page load and tries again.
  let registration: ServiceWorkerRegistration;
  try {
    registration = await navigator.serviceWorker.register("/sw.js", {
      scope: "/",
    });
  } catch (error) {
    console.error("service worker registration failed", error);
    return nothing;
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
      // Serwist, in sw.ts, listens for this message and stops waiting.
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

  // The regular looks (SYNC-13). update() asks the browser to fetch sw.js now: a changed one starts
  // downloading, and "updatefound" above offers it once it has installed. No look while the browser says
  // there is no network: it could only fail. Its coming back is a look of its own, as a laptop that was
  // offline at the hour would otherwise wait for the next one.
  const look = () => {
    if (!navigator.onLine) return;
    // A look that can't reach the server (a router whose mobile data is down) is part of a shop's day:
    // nothing to report, and the next one tries again.
    registration.update().catch(nothing);
  };
  const every = setInterval(look, UPDATE_CHECK_EVERY);
  window.addEventListener("online", look);
  return () => {
    clearInterval(every);
    window.removeEventListener("online", look);
  };
}

function nothing(): void {}
