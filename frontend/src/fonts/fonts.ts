// fonts.ts — the app's two fonts, loaded from the files in this folder (UI-7, ADR-0039).
//
// Counter screens must look the same with no internet, so nothing fetches a font from another
// server, at build time or when the app runs. `next build` puts these files in out/, and the service
// worker stores every file in out/, so offline needs no code of its own (serwist.config.mjs).
//
// The files are Fontsource's Latin versions, which cover Swahili and English. Their fingerprints are
// in fonts.test.ts, so a changed file fails a test:
//   @fontsource-variable/source-sans-3@5.3.1
//   @fontsource-variable/atkinson-hyperlegible-next@5.3.0
//
// Each licence file's first line is the owner's notice from the font's own record, because Fontsource's
// copies said "Google Inc." for Source Sans and repeated the line for Atkinson. The text below it is
// unchanged. Use the files as they come: the Source Sans licence reserves the name "Source", so a copy
// we cut down or convert ourselves would have to take another name.
//
// Same-width digits, read from these files on 5 Nov 2026 (units per 1,000 of the font's size). Measure
// again if a file changes, because money must line up (04 UI-7):
//   Source Sans 3: even as they are, and it has no tnum feature, which it doesn't need. All 497 at weight
//   400, 513 at 600 and 528 at 700. The file's own table says 472, because its default weight is 200.
//   Atkinson: 407 to 648 as they are at weight 400, and all 632 with tnum, which globals.css turns on
//   for the whole page. Chrome measured them even at weights 400, 600 and 700.
//
// Atkinson's Latin file lacks the modifier apostrophe (U+02BC), so that one character falls back to a
// system font. The plain ' and ’ that keyboards type for "ng'ombe" are in both files.
//
// Only layout.tsx imports this file: next/font is Next.js's own build step, so Vitest can't run it.
import localFont from "next/font/local";

// `weight` is a range because each file is a variable font: one file holds every thickness.
// display "swap" shows the words at once in the fallback, then changes to our font when it is ready.
// A blank screen in the middle of a sale would be worse than a moment in the wrong font.
export const sourceSans = localFont({
  src: "./source-sans-3.woff2",
  weight: "200 900",
  variable: "--font-source-sans",
  display: "swap",
  fallback: ["system-ui", "sans-serif"],
});

export const atkinson = localFont({
  src: "./atkinson-hyperlegible-next.woff2",
  weight: "200 800",
  variable: "--font-atkinson",
  display: "swap",
  fallback: ["system-ui", "sans-serif"],
  // Most people use the default font, so the browser needn't hurry for this one. preload only sets
  // the order of loading: the service worker still stores the file for offline use.
  preload: false,
});
