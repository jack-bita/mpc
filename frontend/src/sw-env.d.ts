// sw-env.d.ts — the one `process.env` the service worker's code reads, for its type check only
// (tsconfig.sw.json, SYNC-16).
//
// A worker has no `process`. The app's version (src/lib/version.ts) is written into the code at build
// time, by Next.js for the pages and by esbuild for the worker (serwist.config.mjs, `define`), so the
// name never runs. Declared here, alone, rather than with Node's own types, which would let the worker's
// code use the rest of Node without a word from TypeScript.
declare const process: {
  env: { NEXT_PUBLIC_APP_VERSION?: string };
};
