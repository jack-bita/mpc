// counter-budget.test.ts — the counter screens' size check (SYNC-11, 03 §14): which pages it weighs, which of
// their files it counts, and when it fails. The check itself runs on the real build, after `pnpm build`, in
// `make check-frontend` and so in CI (scripts/counter-budget.mjs); this proves its parts on small made-up
// pages, as the build isn't there when the tests run.
//
// Here beside the script, not in src/: the server image copies src/ but not scripts/ (backend/Dockerfile.dockerignore),
// and its `next build` checks the types of every file in src/, so a test there that imports the script stops the
// image's build.
//
// It runs in plain Node, as it only reads files.
// @vitest-environment node
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import {
  BUDGET,
  counterPages,
  overBudget,
  scriptsOf,
  weigh,
} from "./counter-budget.mjs";

// The made-up folders a test writes, removed after it, so a run leaves nothing behind in the system's temp.
const made: string[] = [];
const aFolder = (name: string) => {
  const folder = mkdtempSync(join(tmpdir(), name));
  made.push(folder);
  return folder;
};
afterEach(() => {
  for (const folder of made.splice(0))
    rmSync(folder, { recursive: true, force: true });
});

describe("the counter screens' size check", () => {
  it("is 300 KB, compressed, as 03 §14 sets it", () => {
    expect(BUDGET).toBe(300 * 1024);
  });

  it("weighs every page of the counter area, found by its files, so a new screen is weighed without a list", () => {
    // The real area: the clock-in screen is its first page (SYNC-11).
    expect(counterPages(join(process.cwd(), "src/app"))).toContain(
      "attendance",
    );
  });

  it("finds a page inside a folder of its own, and leaves the area's other files out", () => {
    const app = aFolder("budget-");
    mkdirSync(join(app, "(counter)/sale/view"), { recursive: true });
    writeFileSync(join(app, "(counter)/layout.tsx"), "");
    writeFileSync(join(app, "(counter)/counter-frame.tsx"), "");
    writeFileSync(join(app, "(counter)/sale/page.tsx"), "");
    writeFileSync(join(app, "(counter)/sale/view/page.tsx"), "");

    expect(counterPages(app).sort()).toEqual(["sale", "sale/view"]);
  });

  it("counts every script a page loads or gets ready to load, each once, and nothing else", () => {
    const html = [
      '<link rel="stylesheet" href="/_next/static/chunks/look.css"/>',
      '<link rel="preload" href="/_next/static/media/font.woff2" as="font"/>',
      '<link rel="preload" as="script" fetchPriority="low" href="/_next/static/chunks/later.js"/>',
      '<script src="/_next/static/chunks/react.js" async=""></script>',
      '<script src="/_next/static/chunks/later.js" async=""></script>',
      "<script>self.__next_f.push([1])</script>",
    ].join("");

    expect(scriptsOf(html).sort()).toEqual([
      "/_next/static/chunks/later.js",
      "/_next/static/chunks/react.js",
    ]);
  });

  it("leaves out a script only browsers too old for the app would load", () => {
    // Next.js's polyfills for browsers with no modules: the shop's Chrome and Edge never fetch them.
    const html = [
      '<script src="/_next/static/chunks/polyfills.js" noModule=""></script>',
      '<script src="/_next/static/chunks/react.js" async=""></script>',
    ].join("");

    expect(scriptsOf(html)).toEqual(["/_next/static/chunks/react.js"]);
  });

  it("weighs a page by its scripts, compressed, as a laptop downloads them", async () => {
    const out = aFolder("budget-out-");
    mkdirSync(join(out, "attendance"), { recursive: true });
    mkdirSync(join(out, "_next/static/chunks"), { recursive: true });
    // Text that repeats squeezes small: 100,000 letters weigh far less once compressed.
    writeFileSync(join(out, "_next/static/chunks/app.js"), "a".repeat(100_000));
    writeFileSync(
      join(out, "attendance/index.html"),
      '<script src="/_next/static/chunks/app.js"></script>',
    );

    const weight = weigh(out, "attendance");

    expect(weight.scripts).toBe(1);
    expect(weight.bytes).toBeGreaterThan(0);
    expect(weight.bytes).toBeLessThan(2_000);
  });

  it("names each page over the budget, and only those", () => {
    const weights = [
      { page: "attendance", scripts: 16, bytes: 280 * 1024 },
      { page: "sale", scripts: 20, bytes: 301 * 1024 },
    ];

    expect(overBudget(weights)).toEqual([weights[1]]);
  });
});
