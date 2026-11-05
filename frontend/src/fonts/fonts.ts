// fonts.ts — the app's two fonts, loaded from the files in this folder (UI-7, ADR-0039).
//
// Counter screens must look the same with no internet, so nothing fetches a font from another
// server, at build time or when the app runs. `next build` puts these files in out/, and the service
// worker stores every file in out/, so offline needs no code of its own (serwist.config.mjs).
//
// The files are Fontsource's Latin versions, at fixed versions, which cover Swahili and English:
//   @fontsource-variable/source-sans-3@5.3.1
//     sha256 19143dca075972bc84e3fd9eab7416dd40cc565dccb2435a044bdfabe060c7d5
//   @fontsource-variable/atkinson-hyperlegible-next@5.3.0
//     sha256 18b2a1a39a2fa298b0ba5390aca68462669826c90925656f1c1f6796e0e1bbaf
//
// Same-width digits, read from these files on 5 Nov 2026 (units per 1,000 of the font's size). Check
// again if a file changes, because money must line up (04 UI-7):
//   Source Sans 3: all 472 as they are; it has no tnum feature and needs none.
//   Atkinson: 407 to 648 as they are, all 632 with tnum, which globals.css turns on for the whole page.
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
