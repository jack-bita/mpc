// query-client.ts — the settings of the office screens' store of server answers (UI-2, 03 §7.1).
//
// TanStack Query keeps each answer the office screens ask for, so two screens asking for the same list
// share one answer, one loading state and one error. What it can't know by itself is which failures are
// worth asking again: that is shouldRetry() below.
import { QueryClient } from "@tanstack/react-query";

import { ApiRefusal } from "./refusal";

// How many times a failed read is asked again, after the first try.
export const READ_RETRIES = 2;

/**
 * Whether a failed read is asked again. A refusal under 500 is the server saying no on purpose: a
 * missing key, a row that isn't there, a password to change. Asking again gets the same no, and the
 * person would wait for it: TanStack's default of 3 more tries takes about 7 seconds. Anything else, a
 * dropped network or a 5xx (often Caddy's 502 while the server restarts), may pass a moment later.
 */
export function shouldRetry(failureCount: number, error: unknown): boolean {
  if (error instanceof ApiRefusal && error.status < 500) return false;
  return failureCount < READ_RETRIES;
}

/** A new store. One per page load (provider.tsx), and one per test, so no answer leaks between them. */
export function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      // Changes keep TanStack's default: never sent again by themselves. A create is safe to send twice
      // (its id is the client's own, 03 §5.10), but an edit sent twice meets its own new version and
      // gets `version_conflict`, so a person decides.
      queries: { retry: shouldRetry },
    },
  });
}
