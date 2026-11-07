// query-client.ts — the settings of the office screens' store of server answers (UI-2, 03 §7.1).
//
// TanStack Query keeps each answer the office screens ask for, so two screens asking for the same list
// share one answer, one loading state and one error. What it can't know by itself is which failures are
// worth asking again: that is shouldRetry() below. And when the person at the device changes, it must
// forget the last one: that is forgetTheLastPerson() (UI-4).
import { QueryClient } from "@tanstack/react-query";

import { ApiRefusal, NoConnection } from "./refusal";

// How many times a failed read is asked again, after the first try.
export const READ_RETRIES = 2;

/**
 * Whether a failed read is asked again. A refusal under 500 is the server saying no on purpose: a
 * missing key, a row that isn't there, a password to change. Asking again gets the same no, and the
 * person would wait for it: TanStack's default of 3 more tries takes about 7 seconds. A bug in the
 * screen would only fail again. A dropped network, or a 5xx (often the proxy's 502 while the server
 * restarts), may pass a moment later: those are asked again.
 */
export function shouldRetry(failureCount: number, error: unknown): boolean {
  return mayPassLater(error) && failureCount < READ_RETRIES;
}

/** Whether a failure may pass if asked again a moment later: a dropped network, or a 5xx. Never a
 * refusal the server meant, nor a bug. Reads ask again a few times (shouldRetry); a logout, until the
 * server hears it (UI-4). */
export function mayPassLater(error: unknown): boolean {
  return (
    error instanceof NoConnection ||
    (error instanceof ApiRefusal && error.status >= 500)
  );
}

/** A new store. One per page load (provider.tsx), and one per test, so no test sees another's answers.
 * Within a page load, everyone who logs in on the device shares it: the login screens empty it at each
 * login, logout and quick switch (forgetTheLastPerson), or the next person would see the last one's rows. */
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

/**
 * Forgets the last person at this device: every answer the store holds and every change sent, and asks
 * again for what the screens on show read. A PIN login, a logout and a quick switch call it (UI-4), and
 * the password's login and logout (UI-5): one browser serves many people, and Juma must never see Asha's
 * rows from her last screen, offline either, where a new read waits for the network.
 */
export async function forgetTheLastPerson(store: QueryClient): Promise<void> {
  // The changes sent, a PIN login among them: each keeps what it was sent with, the PIN too. A change
  // waiting for the network goes too: TanStack sends again only what this list holds when the network is
  // back (resumePausedMutations), so its screen would wait for it for ever. None can be waiting at a PIN
  // login today, as the home page shows only "Unatoka…" while a logout waits (UI-4's review); a screen
  // that sends changes offline and then logs people in must send them first (UI-5).
  store.getMutationCache().clear();
  // Every answer back to nothing, and the screens showing one told, so those on show ask again, for the
  // new person. Not store.clear(): it drops the answers without telling the screens that show them,
  // which then keep the last person's answer until they happen to draw again (TanStack's
  // QueryCache.remove tells only the store's own listeners).
  await store.resetQueries();
}
