// service-worker.ts — registers the service worker (src/sw.ts, built into out/sw.js) from the page
// (SPIKE-1, 03 §7.7).
//
// Registering asks the browser to install /sw.js and keep it for this site. From then on the browser
// checks /sw.js for a new version by itself: whenever the app opens with internet, and about once a day.

/** Asks the browser to install the service worker. Safe on every page load: the browser installs the
 * same sw.js only once. */
export function registerServiceWorker(): void {
  // Only the built app has a service worker: `serwist build` runs after `next build`, and `next dev`
  // serves no /sw.js. Next.js writes the value of NODE_ENV into the code at build time.
  if (process.env.NODE_ENV !== "production") return;
  // Chrome and Edge, the shop's browsers (03 §7.3), have service workers, but an old or locked-down
  // browser may not. The app then still works online, only not offline.
  if (!("serviceWorker" in navigator)) return;
  // scope "/": the worker looks after every page of the app. A failed registration (no internet on the
  // very first visit, say) is only logged: the browser tries again on the next page load.
  navigator.serviceWorker
    .register("/sw.js", { scope: "/" })
    .catch((error: unknown) => {
      console.error("service worker registration failed", error);
    });
}
