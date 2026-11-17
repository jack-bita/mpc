// serwist.config.mjs — how `serwist build` makes the service worker, out/sw.js (SPIKE-1, 03 §7.7).
//
// `pnpm build` runs it right after `next build` (package.json), over the finished files in out/. That way
// we depend on no Next.js bundler plugin: Serwist's support for Turbopack, Next.js's bundler, is still
// settling (03 §7.7, v1.2). `serwist build` then:
//   1. lists every file in out/, each with a fingerprint of its content (its "revision");
//   2. bundles src/sw.ts and the `serwist` package into one plain, minified file with esbuild,
//      writing that list where src/sw.ts says self.__SW_MANIFEST. src/sw.ts itself never changes.
// A deploy that changes any file changes its fingerprint, so sw.js changes too: that is how the browser
// learns that a new version exists (03 §6.8, the update prompt).

/** @type {import("@serwist/cli").BuildOptions} */
const config = {
  swSrc: "src/sw.ts",
  swDest: "out/sw.js",

  // Every file of the build, so every page opens offline: the pages, the code, the styles, the icons,
  // the manifest, and Next.js's .txt files that carry a page's content between pages.
  globDirectory: "out",
  globPatterns: ["**/*"],
  // Not the worker itself: the browser fetches and updates sw.js by its own rules, never from the cache.
  globIgnores: ["sw.js"],

  // Files under _next/static/ are named after their content already (prod.py, _is_named_after_content),
  // so a second fingerprint would only make the list longer.
  dontCacheBustURLsMatching: /^_next\/static\//,

  // The worker pushes the outbox too (SYNC-16), and each push carries the app's version (src/lib/version.ts).
  // Next.js writes it into the pages; esbuild must write the same into the worker, or it would look for a
  // `process` a worker doesn't have. The image build sets it (backend/Dockerfile); elsewhere it is "", which
  // reads as "dev", as on the pages.
  esbuildOptions: {
    define: {
      "process.env.NEXT_PUBLIC_APP_VERSION": JSON.stringify(
        process.env.NEXT_PUBLIC_APP_VERSION ?? "",
      ),
    },
  },
};

export default config;
