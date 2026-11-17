// counter-budget.mjs — fails the check when a counter screen's code grows past its budget: 300 KB compressed
// per screen (03 §14, SYNC-11). It owns how a screen is weighed.
//
// Why a budget: a shop laptop or the shop's Android phone opens the counter many times a day, often on a slow
// line, and an app that grew a little at every card would one day open slowly with nobody able to say which
// change did it. The check names the screen and its weight the day it passes the line, in the pull request
// that did it.
//
// How a screen is weighed, after `pnpm build`:
//   1. its page is every page.tsx under src/app/(counter)/, found by its file, so a new screen is weighed
//      with no list to keep: (counter)/attendance/page.tsx is out/attendance/index.html;
//   2. its code is every script that page loads or gets ready to load (<script src>, and <link as="script">,
//      which Next.js uses for a chunk it fetches soon after), each counted once, but a nomodule script,
//      which only browsers too old for the app fetch;
//   3. each file is compressed with gzip, as a server sends it, and the sizes added up. Gzip, not the smaller
//      brotli a browser may also accept: the weight a slow line can count on.
// Only scripts: the code a laptop must download and run before the screen works. The shared stylesheet and
// the fonts are counted by nobody yet.
//
// Most of a screen's weight is what every page shares (React, Next.js, the word books, Dexie, the sync): the
// clock-in screen itself adds about 1.4 KB of its 234.6 (SYNC-11).
//
// Honest limit: a chunk a screen fetches later with a dynamic import() isn't named in its page, so it isn't
// weighed; the screen's first load is.
//
// Run from frontend/, after the build:
//   node scripts/counter-budget.mjs
// `make check-frontend` runs it after `pnpm build`, so CI runs it too. It needs only Node's own modules. Its test is
// beside it (counter-budget.test.ts).
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import { gzipSync } from "node:zlib";

/** The budget per counter screen, in bytes, compressed: 300 KB (03 §14, a default). */
export const BUDGET = 300 * 1024;

/** The counter area's folder, a route group: its name stays out of the pages' addresses. */
const COUNTER_AREA = "(counter)";

/**
 * The counter screens' addresses, from the page files under `appDir`'s counter area: "attendance" for
 * (counter)/attendance/page.tsx. A folder in brackets inside it is a route group too, and stays out of the
 * address, as Next.js leaves it out.
 * @param {string} appDir the app's folder, src/app
 * @returns {string[]}
 */
export function counterPages(appDir) {
  const area = join(appDir, COUNTER_AREA);
  return readdirSync(area, { recursive: true, encoding: "utf8" })
    .map((file) => file.split("\\").join("/"))
    .filter((file) => /(^|\/)page\.(tsx|ts|jsx|js)$/.test(file))
    .map((file) =>
      file
        .split("/")
        .slice(0, -1)
        .filter((part) => !/^\(.*\)$/.test(part))
        .join("/"),
    );
}

/**
 * The scripts a built page loads, or gets ready to load, by their addresses, each once.
 * @param {string} html the page's built HTML
 * @returns {string[]}
 */
export function scriptsOf(html) {
  const found = new Set();
  for (const [tag] of html.matchAll(/<script\b[^>]*>/g)) {
    // A nomodule script is for browsers too old to run modules: every browser this app supports skips it,
    // without downloading it (03 §7.3). Next.js adds one, its old-browser polyfills, of about 40 KB.
    if (/\snomodule\b/i.test(tag)) continue;
    const src = /\ssrc="([^"]+)"/.exec(tag)?.[1];
    if (src !== undefined) found.add(src);
  }
  // A link that gets a script ready: as="script", before or after its href.
  for (const [tag] of html.matchAll(/<link\b[^>]*>/g)) {
    if (!/\sas="script"/.test(tag)) continue;
    const href = /\shref="([^"]+)"/.exec(tag)?.[1];
    if (href !== undefined) found.add(href);
  }
  return [...found];
}

/**
 * A built screen's weight: how many scripts, and their bytes once compressed.
 * @param {string} outDir the build's folder, out/
 * @param {string} page the screen's address, as counterPages gives it
 * @returns {{ page: string, scripts: number, bytes: number }}
 */
export function weigh(outDir, page) {
  const file = join(outDir, page, "index.html");
  if (!existsSync(file))
    throw new Error(
      `${file} is missing: build the app first (pnpm build), from frontend/.`,
    );
  const scripts = scriptsOf(readFileSync(file, "utf8"));
  let bytes = 0;
  // Addresses start at the site's root ("/_next/…"), which is out/ in the build.
  for (const script of scripts)
    bytes += gzipSync(readFileSync(join(outDir, script))).length;
  return { page, scripts: scripts.length, bytes };
}

/**
 * The screens over the budget, in the order given.
 * @param {{ page: string, scripts: number, bytes: number }[]} weights
 */
export function overBudget(weights) {
  return weights.filter((weight) => weight.bytes > BUDGET);
}

const kilobytes = (bytes) => `${(bytes / 1024).toFixed(1)} KB`;

function main() {
  const pages = counterPages("src/app");
  if (pages.length === 0) {
    console.error(
      "FAIL: no counter screen found under src/app/(counter)/: nothing to weigh.",
    );
    process.exit(1);
  }
  const weights = pages.map((page) => weigh("out", page));
  console.log(
    `Counter screens' code, compressed (budget ${kilobytes(BUDGET)} each, 03 §14):`,
  );
  for (const { page, scripts, bytes } of weights)
    console.log(
      `  /${page}/  ${kilobytes(bytes)} in ${scripts} scripts${bytes > BUDGET ? "  OVER" : ""}`,
    );
  const over = overBudget(weights);
  if (over.length > 0) {
    console.error(
      `FAIL: ${over.map((weight) => `/${weight.page}/`).join(", ")} over the counter budget. Find what grew ` +
        "(a new package, a big import on a counter screen) and load it later or leave it out, or raise the " +
        "budget in 03 §14 with a reason.",
    );
    process.exit(1);
  }
}

// Run as a command, not when a test imports it.
if (import.meta.url === pathToFileURL(process.argv[1] ?? "").href) main();
