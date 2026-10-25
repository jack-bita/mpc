// serwist.config.mjs — how `serwist build` makes the service worker, out/sw.js (SPIKE-1, 03 §7.7).
//
// `pnpm build` runs it right after `next build` (package.json), over the finished files in out/. That way
// we depend on no Next.js bundler plugin: Serwist's support for Turbopack, Next.js's bundler, is still
// settling (03 §7.7, v1.2). `serwist build` then:
//   1. lists every file in out/, each with a fingerprint of its content (its "revision");
//   2. writes that list into src/sw.ts in place of self.__SW_MANIFEST;
//   3. bundles the worker and the `serwist` package into one plain file with esbuild, minified.
// A deploy that changes any file changes its fingerprint, so sw.js changes too: that is how the browser
// learns that a new version exists (lesson 2, the update prompt).

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
};

export default config;
