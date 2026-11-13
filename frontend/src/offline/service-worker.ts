// service-worker.ts — registers the service worker (src/sw.ts, built into out/sw.js) from the page, says
// when a new version is waiting, and looks for one regularly (SPIKE-1, SYNC-13, 03 §6.8, §7.7).
//
// Registering asks the browser to install /sw.js and keep it for this site. From then on the browser
// checks /sw.js for a new version by itself each time a page of the app loads with internet. It sets
// no timer of its own: a counter left open all day would see a deploy only after a reload (SPIKE-1). So
// the page asks it to look every UPDATE_CHECK_EVERY, when the network comes back, and as soon as a sync
// finds the app too old for the server (SYNC-13, sync/too-old.ts).
// A new version downloads in the background, then waits (sw.ts: skipWaiting false) until the Toleo jipya
// bar switches, at a tap of Sasisha or by itself for an app too old for the server, each once the counter
// is quiet, or until every window of the app is closed: the app must never reload in the middle of a sale
// (03 §6.8). A tab another tab switched is offered a reload too, as its old code can't run on the new
// version's files.

import { listenForTooOld } from "./sync/too-old";

/** Switches to the waiting version: the new worker takes over, then the page reloads from it. */
export type ApplyUpdate = () => void;

/** What an offered switch is: a new version waiting to take over, or one that has taken over already,
 * as another tab switched, while this page still runs the old version's code. */
export type UpdateKind = "waiting" | "taken_over";

/** How often an open app asks the browser to look for a new version (03 §6.8, a default): a deploy
 * reaches a counter left open all day within the hour. Each look fetches only sw.js, a small file, and
 * downloads the rest only when it has changed. */
export const UPDATE_CHECK_EVERY = 60 * 60 * 1000;

/**
 * Asks the browser to install the service worker, calls `onUpdateReady` when a new version waits, and
 * looks for one every UPDATE_CHECK_EVERY, when the network comes back and when the app is too old, until
 * the function it hands back is called. Safe on every page load: the browser installs the same sw.js
 * only once.
 * `reload` is replaced only by tests, because jsdom can't reload a page.
 */
export async function registerServiceWorker(
  onUpdateReady: (apply: ApplyUpdate, kind: UpdateKind) => void,
  reload: () => void = () => window.location.reload(),
): Promise<() => void> {
  // Only the built app has a service worker: `serwist build` runs after `next build`, and `next dev`
  // serves no /sw.js. Next.js writes the value of NODE_ENV into the code at build time.
  if (process.env.NODE_ENV !== "production") return nothing;
  // Chrome and Edge, the shop's browsers (03 §7.3), have service workers, but an old or locked-down
  // browser may not. The app then still works online, only not offline.
  if (!("serviceWorker" in navigator)) return nothing;

  // A new version took over (SYNC-13), at this page's own ask or another tab's: it now serves this page,
  // but the page still runs the old version's code, and the new worker has deleted the old version's files
  // (SPIKE-1). The first screen that needs one of them would fail, perhaps in the middle of a sale. So this
  // page is offered a reload, taken over: the bar reloads it by itself once the counter is quiet, as it
  // updates an app too old for the server (update-prompt.tsx). Not when no version ran the page before, the
  // very first install (sw.ts: clientsClaim), as nothing old is in it; a page that first install took
  // charge of is run by a version from then on, so a later switch is offered. Noted, and heard, before
  // registering, which waits for the browser after the page's first paint: a switch another tab makes in
  // that moment would otherwise reach no listener, and the page would stay on the old code.
  let ranBy = navigator.serviceWorker.controller;
  const tookOver = () => {
    const before = ranBy;
    ranBy = navigator.serviceWorker.controller;
    if (before === null) return;
    onUpdateReady(() => reload(), "taken_over");
  };
  navigator.serviceWorker.addEventListener("controllerchange", tookOver);

  // scope "/": the worker looks after every page of the app. A failed registration (sw.js missing or
  // of the wrong type, the connection dropping, service workers switched off) is only logged: this
  // function runs again on the next page load and tries again. Nothing is heard until then.
  let registration: ServiceWorkerRegistration;
  try {
    registration = await navigator.serviceWorker.register("/sw.js", {
      scope: "/",
    });
  } catch (error) {
    console.error("service worker registration failed", error);
    navigator.serviceWorker.removeEventListener("controllerchange", tookOver);
    return nothing;
  }

  // An update is something to offer only when a version already runs this page. On the very first
  // install there is nothing to replace: the new worker takes charge by itself (sw.ts: clientsClaim).
  const offer = (worker: ServiceWorker) => {
    if (!navigator.serviceWorker.controller) return;
    onUpdateReady(() => {
      // Past "installed", the new version is taking over or has taken over already: another tab
      // switched first. The browser announced it (controllerchange) as the version began taking over,
      // so waiting for that announcement now would wait forever. Only this page is old, and the bar
      // looked at the counter just now: reload it.
      if (worker.state !== "installed") {
        reload();
        return;
      }
      // Serwist, in sw.ts, listens for this message and stops waiting. The reload comes once the new
      // version has taken over, so the reloaded page comes from it: offered below (tookOver), as to every
      // other tab, never done on the spot. Taking over can take a while, as the new version waits for the
      // old one's last work, a background push say, and a sale started meanwhile must finish first.
      worker.postMessage({ type: "SKIP_WAITING" });
    }, "waiting");
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
  // Too old to sync: the pulls have stopped, so the new version is wanted now, not within the hour. Each
  // sync that finds it looks again, in case the last look failed.
  const stopHearing = listenForTooOld(look);
  return () => {
    clearInterval(every);
    window.removeEventListener("online", look);
    stopHearing();
    navigator.serviceWorker.removeEventListener("controllerchange", tookOver);
  };
}

function nothing(): void {}
