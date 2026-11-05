// manifest.ts — the web app manifest: what Chrome needs before it offers to install the shop app
// (SPIKE-1, 03 §7.7).
//
// Next.js turns this function into out/manifest.webmanifest at build time, and links it from every
// page for us (<link rel="manifest">). It runs once, during the build: no server runs it later (ADR-0016).
import type { MetadataRoute } from "next";

// The app's name is screen text, so it comes from the message files, like all screen text (ADR-0032).
import sw from "../../messages/sw.json";

// Make the manifest once, at build time, into a plain file. Next.js treats this file like a small
// route that could run on a server for each request; a static export has no server (ADR-0016), so
// the build refuses until the file says so.
export const dynamic = "force-static";

export default function manifest(): MetadataRoute.Manifest {
  return {
    // The app's identity. Without it Chrome would use start_url, which will change for counter
    // devices (03 §7.7): a new identity would make every installed copy a different app.
    id: "/",
    name: sw.app.title,
    short_name: sw.app.title,
    // Swahili first (ADR-0032): the language of the name and of the app.
    lang: "sw",
    start_url: "/",
    // A window of its own, with no address bar: it looks and feels like an app.
    display: "standalone",
    // The colour of the title bar, and of the screen while the app starts: the shop's green. A
    // manifest is plain data and can't read a token, so manifest.test.ts holds this equal to --primary
    // in globals.css (ADR-0039).
    theme_color: "#15803d",
    background_color: "#15803d",
    // PNG, in the two sizes Chrome asks for. The files are drawn by scripts/make-icons.mjs.
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
      // Android cuts icons into a circle or a rounded square; this one draws the godown smaller, in
      // the safe middle, so the cut never reaches it.
      {
        src: "/icons/icon-maskable-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "maskable",
      },
    ],
  };
}
