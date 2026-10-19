// next.config.ts — how Next.js builds the shop app.
//
// The app is built into plain files (HTML, JS, CSS) in out/, and no Node server runs in
// production (ADR-0016, 03 AD2). Why: the counter must open with no internet, and a page
// rendered on a server can't open when the server is out of reach. A service worker
// (SPIKE-1) will keep these files on each shop device.
//
// What a static build costs us (03 §7.2):
// - every page is a client component; no server actions, middleware or route handlers;
// - no dynamic [id] pages, because records don't exist at build time: a record page
//   reads its id from the query string (/sales/view?id=…).
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Write plain files to out/ instead of running a Node server.
  output: "export",

  // Next's image optimiser resizes images on a server, at request time. A static build has
  // no server, so images are served exactly as they sit in public/.
  images: { unoptimized: true },

  // Write sale/index.html instead of sale.html, so a file server finds each page by its
  // folder. Caddy's file_server (the `web` image, OPS-5) serves a folder's index.html by
  // default; WhiteNoise (OPS-1) does too once WHITENOISE_INDEX_FILE = True.
  trailingSlash: true,
};

export default nextConfig;
