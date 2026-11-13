// sw.ts — the service worker: keeps every file of the app on the device, so the app opens with no
// internet (SPIKE-1, ADR-0016, 03 §7.7).
//
// The browser runs it in the background, apart from the pages, and every request a page makes passes
// through it. It is not part of the Next.js build: `serwist build` (serwist.config.mjs) bundles it after
// `next build` into out/sw.js, and writes the list of the app's files in place of self.__SW_MANIFEST.
//
// It also sends what waits in the outbox when the network comes back, even with the app closed: Background
// Sync, where the browser has it (SYNC-16, 03 §6.5; the push itself is background.ts).
import { type PrecacheEntry, Serwist } from "serwist";

import { CSRF_COOKIE, CSRF_HEADER, createApiClient } from "./api/make-client";
import { backgroundPush, shopOfTag } from "./offline/sync/background";

// Background Sync's event, which TypeScript's own types don't have yet: its name, and waitUntil, which
// keeps the worker alive until the push ends, and tells the browser to try again if it failed.
interface SyncEvent extends ExtendableEvent {
  readonly tag: string;
}

// Two facts TypeScript can't know by itself:
// - `self` is this service worker, not a window (tsconfig.sw.json gives it the worker's types);
// - `self.__SW_MANIFEST` is the list of files that `serwist build` writes in.
declare const self: ServiceWorkerGlobalScope & {
  __SW_MANIFEST: (PrecacheEntry | string)[] | undefined;
  addEventListener(type: "sync", listener: (event: SyncEvent) => void): void;
};

const serwist = new Serwist({
  // The list of the app's files, each with its fingerprint. When the worker installs, it downloads
  // them all into the cache (03 §7.7).
  precacheEntries: self.__SW_MANIFEST,
  // Find a file in the cache whatever follows the "?" in its address. Next.js asks for a page's data
  // as /page/index.txt?_rsc=…, and record pages will carry their id the same way (/sales/view/?id=…,
  // ADR-0016), but the cache keeps each file once, under its address without the "?". Safe because no
  // file of the build changes with what follows the "?", and /api answers are never cached.
  precacheOptions: {
    ignoreURLParametersMatching: [/.*/],
  },
  // A new version waits until someone taps Sasisha, or until every window of the app is closed: the
  // app must never reload in the middle of a sale (03 §6.7). With skipWaiting false, Serwist itself
  // listens for the update bar's SKIP_WAITING message, and then stops waiting.
  skipWaiting: false,
  // The very first time, take charge of the open page at once, so it works offline with no reload.
  // A later version still waits, because of skipWaiting above.
  clientsClaim: true,
  // No runtimeCaching: only the build's own files are kept. Answers from /api never are, because the
  // shop's data lives in Dexie (03 §7.7).
});

// Start listening for the browser's events: install (download the files into the cache), activate
// (delete the old version's files) and fetch (answer each request from the cache).
serwist.addEventListeners();

// The CSRF cookie, read with the Cookie Store, the way a worker can: it has no document.cookie. Read at
// each change, never kept, as the page's client does (client.ts: a login gives a new token). Every
// browser with Background Sync has it; one without simply sends no token, and is refused.
async function csrfHeader(): Promise<Record<string, string>> {
  const token = (await self.cookieStore?.get(CSRF_COOKIE))?.value;
  return token ? { [CSRF_HEADER]: token } : {};
}

const tools = {
  api: createApiClient({}, csrfHeader),
  hasCsrfToken: async () => Object.keys(await csrfHeader()).length > 0,
};

// The browser wakes the worker when the network is there for a sync the page asked for. A name that
// isn't ours is left alone.
self.addEventListener("sync", (event) => {
  const shopId = shopOfTag(event.tag);
  if (shopId !== null) event.waitUntil(backgroundPush(shopId, tools));
});
