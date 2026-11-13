// busy.ts — the counter's busy mark: a counter screen in the middle of work says so, and an update waits
// until no screen, in any tab of the app, is busy (SYNC-13, 03 §6.8).
//
// Switching to a new version reloads the page, and a reload in the middle of a sale loses the sale: the
// items typed, the customer waiting. So the Toleo jipya bar shows only while the counter is quiet (Jack,
// 13 Nov 2026: the bar stays hidden until the sale is finished, then shows, and the seller taps it). A
// screen marks itself busy with useCounterBusy(true) while its work is open, as the sale screen will while
// it has items in it; a one-tap screen, as the clock-in, has nothing open to lose and never does.
//
// Another tab's screen counts too: the new version takes over every tab at once, and an old tab still
// open is then served by a worker that has deleted the old version's files (SPIKE-1). Tabs share the
// browser's Web Locks (lock.ts): each busy screen holds a shared lock of one name, BUSY_LOCK, and the bar
// asks the browser whether anyone holds it. Shared, because many screens may be busy at once; held as
// long as the screen is busy, and let go by the browser by itself when its tab closes, mid-sale too, so
// a closed tab never keeps the update away for good.
//
// A browser without Web Locks, and the tests' plain jsdom, count this tab's screens only (lock.ts says
// which browsers).
import { useEffect, useState } from "react";

/** The shared lock every busy counter screen holds, in every tab. Not a shop's own, as the sync's lock
 * is: the app's version is the whole browser's, whichever shop its tabs show. Never rename it: during an
 * update an old tab and a new one run side by side, two versions of this file, and each must see the
 * other's marks. */
export const BUSY_LOCK = "mpc-counter-busy";

/** How often a watching bar looks again (useCounterQuiet). Another tab tells this one nothing when its
 * screen is done, or when it closes: the bar shows at most this long after the counter went quiet. */
export const QUIET_CHECK_EVERY = 2_000;

// This tab's busy screens, counted, for a browser with no Web Locks and for an answer with no wait; and
// the watchers to tell when the count changes.
let busyHere = 0;
const watchers = new Set<() => void>();

function tellWatchers(): void {
  for (const look of watchers) look();
}

function hasLocks(): boolean {
  return "locks" in navigator;
}

/**
 * Marks the screen busy while `busy` is true: no update switches the app until it is false again, or the
 * screen has left the page. Call it with the screen's own state, `useCounterBusy(items.length > 0)`.
 */
export function useCounterBusy(busy: boolean): void {
  useEffect(() => {
    if (!busy) return;
    busyHere += 1;
    let letGo = nothing;
    if (hasLocks()) {
      const done = new Promise<void>((resolve) => {
        letGo = resolve;
      });
      // Held until `done` settles. The watchers hear again once the browser has let it go, not before:
      // a look straight after letGo() could still find it held, and the bar would wait for its next look.
      // A refused ask (the page is closing) tells them too: there is no lock to wait for.
      navigator.locks
        .request(BUSY_LOCK, { mode: "shared" }, () => done)
        .then(tellWatchers, tellWatchers);
    }
    tellWatchers();
    return () => {
      busyHere -= 1;
      letGo();
      tellWatchers();
    };
  }, [busy]);
}

/** Whether no counter screen is busy, in this tab or, where the browser has Web Locks, in any other. */
export async function counterIsQuiet(): Promise<boolean> {
  if (busyHere > 0) return false;
  if (!hasLocks()) return true;
  // Waiting counts as busy too: a screen that has just asked for its mark is busy already.
  const { held = [], pending = [] } = await navigator.locks.query();
  return ![...held, ...pending].some((lock) => lock.name === BUSY_LOCK);
}

/**
 * Whether the counter is quiet, kept up to date while `watching` is true: at once when a screen of this
 * tab changes, and every QUIET_CHECK_EVERY for the other tabs. False while it isn't watching, and until
 * its first look has answered: the bar stays hidden rather than flash up over a busy screen.
 */
export function useCounterQuiet(watching: boolean): boolean {
  const [quiet, setQuiet] = useState(false);
  useEffect(() => {
    if (!watching) return;
    // Only the latest look's answer counts: two looks in flight may answer out of order, and the older
    // one would show a counter that has changed since.
    let looks = 0;
    let stopped = false;
    const look = () => {
      const mine = ++looks;
      void counterIsQuiet().then((answer) => {
        if (!stopped && mine === looks) setQuiet(answer);
      });
    };
    look();
    watchers.add(look);
    const every = setInterval(look, QUIET_CHECK_EVERY);
    return () => {
      stopped = true;
      watchers.delete(look);
      clearInterval(every);
      // Watching again later starts from "busy" until its first look, as at the start.
      setQuiet(false);
    };
  }, [watching]);
  return watching && quiet;
}

function nothing(): void {}
