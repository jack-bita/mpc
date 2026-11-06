// vitest.setup.ts — runs before every test file (see vitest.config.mts).
//
// Empty the fake page after each test. Testing Library only does this by itself when test
// functions are global, and ours are imported from "vitest". Without it, what one test
// rendered stays on the page and can make the next test pass or fail for the wrong reason.
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(() => {
  cleanup();
  // The language a test chose is kept in the browser's storage (src/i18n/language.ts): forget it, so
  // the next test opens in Swahili, as a new device does. Tests that run in plain Node have no storage.
  if (typeof window !== "undefined") window.localStorage.clear();
});
