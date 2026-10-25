// sw.ts — the service worker: keeps every file of the app on the device, so the app opens with no
// internet (SPIKE-1, ADR-0016, 03 §7.7).
//
// The browser runs it in the background, apart from the pages, and every request a page makes passes
// through it. It is not part of the Next.js build: `serwist build` (serwist.config.mjs) bundles it after
// `next build` into out/sw.js, and writes the list of the app's files in place of self.__SW_MANIFEST.
import { type PrecacheEntry, Serwist } from "serwist";

// Two facts TypeScript can't know by itself:
// - `self` is this service worker, not a window (tsconfig.sw.json gives it the worker's types);
// - `self.__SW_MANIFEST` is the list of files that `serwist build` writes in.
declare const self: ServiceWorkerGlobalScope & {
  __SW_MANIFEST: (PrecacheEntry | string)[] | undefined;
};

const serwist = new Serwist({
  // The list of the app's files, each with its fingerprint. When the worker installs, it downloads
  // them all into the cache (lesson 2).
  precacheEntries: self.__SW_MANIFEST,
  // Find a file in the cache whatever follows the "?" in its address. Next.js asks for a page's data
  // as /page/index.txt?_rsc=…, and record pages will carry their id the same way (/sales/view/?id=…,
  // ADR-0016), but the cache keeps each file once, under its address without the "?". Safe because no
  // file of the build changes with what follows the "?", and /api answers are never cached.
  precacheOptions: {
    ignoreURLParametersMatching: [/.*/],
  },
  // A new version waits until someone taps Toleo jipya: the app must never reload in the middle of a
  // sale (03 §6.7). The update prompt sends SKIP_WAITING instead (below).
  skipWaiting: false,
  // The very first time, take charge of the open page at once, so it works offline with no reload.
  // A later version still waits, because of skipWaiting above.
  clientsClaim: true,
  // No runtimeCaching: only the build's own files are kept. Answers from /api never are, because the
  // shop's data lives in Dexie (03 §7.7).
});

// The update prompt sends this message when someone taps Toleo jipya: the waiting version stops
// waiting and takes over.
self.addEventListener("message", (event) => {
  if (event.data?.type === "SKIP_WAITING") void self.skipWaiting();
});

// Start listening for the browser's events: install (download the files into the cache), activate
// (delete the old version's files) and fetch (answer each request from the cache).
serwist.addEventListeners();
