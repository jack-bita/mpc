// router.ts — a stand-in for Next.js's router, for tests (UI-5). Tests only.
//
// A screen that moves to another page by itself, as the login form does once it worked, asks
// next/navigation's useRouter(), which works only inside a running Next.js app. vitest.setup.ts swaps it
// for this one in every test file, so such a page renders in any test, the language test's tour of
// every page included. A test reads from `router` where the screen sent the person, and the setup
// forgets it after each test.
import { vi } from "vitest";

export const router = {
  push: vi.fn(),
  replace: vi.fn(),
  back: vi.fn(),
  forward: vi.fn(),
  refresh: vi.fn(),
  prefetch: vi.fn(),
};

/** Forgets where every screen sent the person: vitest.setup.ts calls it after each test. */
export function resetRouter(): void {
  for (const call of Object.values(router)) call.mockReset();
}
