// too-old.ts — this app is too old to sync, and must update (SYNC-13, 03 §6.8).
//
// A pull says so in two ways (pull.ts, AppTooOld): the server's minimum app number is above this app's
// (APP_NUMBER, src/lib/version.ts), or a page names a list this app has no drawer for. Either way the pull
// stops before that page, its cursor where it was, so nothing is passed over, and until the app updates it
// gets no change from the office, a suspension included. The push before it has gone already (sync.ts):
// the records go first, as 03 §6.8 asks.
//
// The sync tells it here (triggers.tsx, reportSyncFailure); two listen: the service worker's looks, which
// look for the new version at once (service-worker.ts), and the update bar, which switches by itself, with
// no tap, as soon as a version is ready and the counter is quiet (update-prompt.tsx; Jack, 13 Nov 2026).
// This file imports nothing, so either side may use it.
//
// Kept in this tab's memory only. Every tab syncs, so each learns it at its own next sync; a reload
// forgets it, and the next sync tells it again.

type Listener = () => void;

// How many times a sync of this tab has found the app too old: a count, not a yes or no, so each telling
// is news to whoever reads it (timesTold).
let told = 0;
const listeners = new Set<Listener>();

/** A pull found this app too old. Told again at every sync that finds it: each is one more look for the
 * new version, in case the last look failed, and one more try at switching, in case the last try met a
 * busy counter. */
export function tellAppTooOld(): void {
  told += 1;
  for (const listener of listeners) listener();
}

/** Whether a sync of this tab has found the app too old. */
export function appIsTooOld(): boolean {
  return told > 0;
}

/** How many times a sync of this tab has found the app too old. The update bar reads this, not the yes or
 * no: React redraws only when what it reads changes, and the bar must try again at each telling. A try
 * that another tab's sale refused, which was finished before the bar's next look, changes nothing else the
 * bar reads, so without a new count the bar would never try again, its pulls stopped, until a tap. */
export function timesTold(): number {
  return told;
}

/** Hears each time a sync finds the app too old; the returned function stops listening. */
export function listenForTooOld(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** Tests only: a new tab, which has heard nothing (vitest.setup.ts). */
export function forgetTooOld(): void {
  told = 0;
}
