// vitest.setup.ts — runs before every test file (see vitest.config.mts).
//
// Empty the fake page after each test. Testing Library only does this by itself when test
// functions are global, and ours are imported from "vitest". Without it, what one test
// rendered stays on the page and can make the next test pass or fail for the wrong reason.
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(() => {
  cleanup();
});
