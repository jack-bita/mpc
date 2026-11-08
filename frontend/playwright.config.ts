// playwright.config.ts — how the browser tests run (UI-6, 03 §11).
//
// It owns Playwright's settings: where the tests live (e2e/), which browser drives them, which address
// they open, and what is kept when one fails.
//
// What they run against: the backend image, started with a fresh PostgreSQL by compose.e2e.yml. That one
// container serves the API and the built app from one address, as on the demo (03 §13), so the tests see
// what a shop's laptop gets: the production build with its service worker, never `next dev`.
// `make check-e2e` builds the image, starts that pair, runs `pnpm e2e` and wipes it (scripts/run_e2e.sh).
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  // One test at a time. The tests share one database, and a story's steps depend on each other (a laptop
  // is paired before anyone logs in at it), so tests side by side would only trip over each other's rows.
  workers: 1,
  fullyParallel: false,
  // No second tries: a test that passes only on its second go hides a real fault, a race in the app or in
  // the test. It must fail, and be fixed.
  retries: 0,
  // A `test.only` left in by mistake would quietly skip every other test, and the run would still pass. So it
  // fails the run, on a laptop as on CI, as `make check` must run exactly what CI runs (ops rule). To run
  // one test while working on it, name its file instead: `pnpm exec playwright test e2e/<file>`.
  forbidOnly: true,
  // Each test's line as it runs. On CI also an HTML report, which the e2e job keeps when a test fails
  // (.github/workflows/ci.yml), with the trace and screenshot below inside it.
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    // localhost, never 127.0.0.1: the production settings mark the session and CSRF cookies Secure
    // (backend/config/settings/prod.py), and over plain http Chrome takes Secure cookies from localhost
    // only. 8090 is free beside `make dev`'s 8080, 8000 and 3000. E2E_BASE_URL points the tests elsewhere.
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:8090",
    // As at the shop: a Swahili browser on Tanzania's clock. The app opens in Swahili whatever the browser
    // says (src/i18n/language.ts), but dates and times read the browser's zone.
    locale: "sw-TZ",
    timezoneId: "Africa/Dar_es_Salaam",
    // On a failure only: a trace (each step, the page at that moment, the network) and a screenshot, to
    // see what the robot saw. Kept on every run, they would only slow it down.
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  // Chromium only: the shop's laptops and phones run Chrome, or Edge, which is built on Chromium too.
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
