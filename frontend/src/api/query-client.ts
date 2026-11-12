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
      // Every change in one queue, sent one at a time, in the order it was made: a scope (TanStack runs
      // the changes of one scope one after another, and holds the next back while one is on its way, offline
      // too). Asha renames a laptop with no network, then presses Toka: back online, the two would go at once,
      // and a logout that landed first would leave the rename refused, and lost. In one queue, the rename
      // goes first, then the logout, which forgets the person once both are done (UI-5's review).
      mutations: { scope: { id: CHANGES_IN_ORDER } },
    },
  });
}

/** The one queue every change waits in (makeQueryClient). */
export const CHANGES_IN_ORDER = "changes-in-order";

/**
 * Forgets the last person at this device: every answer the store holds and every change done, and asks
 * again for what the screens on show read. A PIN login, a logout and a quick switch call it (UI-4), and
 * the password's login and logout (UI-5): one browser serves many people, and Juma must never see Asha's
 * rows from her last screen, offline either, where a new read waits for the network. A change still on
 * its way keeps its place in the queue (SYNC-10's review).
 */
export async function forgetTheLastPerson(store: QueryClient): Promise<void> {
  // The changes done, a PIN login among them: each keeps what it was sent with, the PIN too. Not one still
  // on its way. Taken off the list, such a change doesn't stop: TanStack's tries go on outside the list.
  // It only loses its place in the queue (CHANGES_IN_ORDER), so a change made after it could pass it, and
  // one waiting for the network would never be sent, as TanStack sends again only what the list holds when
  // the network is back (resumePausedMutations). So a logout waiting for the network, forgotten as someone
  // logs in on the laptop's own check, would wake later and end the next person's online login (SYNC-10).
  // Kept, it goes in its turn, as the person who made it meant, and is let go of once done.
  const changes = store.getMutationCache();
  for (const change of changes.getAll())
    if (change.state.status !== "pending") changes.remove(change);
  // Every answer back to nothing, and the screens showing one told, so those on show ask again, for the
  // new person. Not store.clear(): it drops the answers without telling the screens that show them,
  // which then keep the last person's answer until they happen to draw again (TanStack's
  // QueryCache.remove tells only the store's own listeners).
  await store.resetQueries();
}
