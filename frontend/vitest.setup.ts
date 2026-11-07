// vitest.setup.ts — runs before every test file (see vitest.config.mts).
//
// After each test, it empties what a test leaves behind: the fake page, the browser's storage and
// the fake server. Testing Library only empties the page by itself when test functions are global,
// and ours are imported from "vitest". Without it, what one test rendered stays on the page and can
// make the next test pass or fail for the wrong reason.
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

import { resetFakeServer } from "@/test/fake-server";
import { resetRouter } from "@/test/router";

// Next.js's router works only inside a running Next.js app: every test file gets the stand-in in
// src/test/router.ts in its place, so a screen that moves to another page renders in any test (UI-5).
// The rest of next/navigation stays the real one.
vi.mock("next/navigation", async (importOriginal) => {
  const { router } = await import("@/test/router");
  return {
    ...(await importOriginal<typeof import("next/navigation")>()),
    useRouter: () => router,
  };
});

afterEach(() => {
  cleanup();
  // The language a test chose is kept in the browser's storage (src/i18n/language.ts): forget it, so
  // the next test opens in Swahili, as a new device does. Tests that run in plain Node have no storage.
  // The same for the device's saved copy (src/features/devices/this-device.ts), so each test starts as
  // a new device, not yet registered.
  if (typeof window !== "undefined") window.localStorage.clear();
  // The fake server's routes and the requests it saw (src/test/fake-server.ts), so no test meets
  // another's answers.
  resetFakeServer();
  // Where a screen sent the person (src/test/router.ts).
  resetRouter();
});
