// triggers.tsx — when this laptop syncs (SYNC-9, 03 §6.5): as the app opens, when the network comes back,
// 2 s after a record is saved, every 30 s while online, and when someone presses Tuma sasa; and what a
// failed sync leaves.
//
// Each moment asks syncShop (sync.ts), which runs one sync at a time in this tab, and once more after it
// when asked meanwhile: moments that land together cost one extra sync at most.
//
// No moment while the network is gone. navigator.onLine false is sure: no network at all (network.ts), so
// a sync could only fail, and each failed push makes the next one wait longer (backoff.ts): an afternoon
// offline would leave the records waiting 5 minutes after the network came back. Its coming back is a
// moment of its own. True is not sure (a router whose mobile data is down): the sync then fails as any
// sync with no answer does, and the next moment tries again.
//
// The device check (device-check.tsx) started a sync after each of its answers until this card. It still
// asks the server about the device on its own times, and starts none. A window back in front is no
// moment: the 30 s covers it.
//
// The root layout puts it on every page, the counter's included. That is not a counter screen asking the
// server (rule 5): it is the laptop's sync, beside every screen, as the device check is. A counter screen
// asks for a sync through asks.ts, which calls nothing. It shows nothing.
//
// "use client": it runs in the browser, and the build has none.
"use client";

import { useEffect } from "react";

import { ApiRefusal, NoConnection } from "@/api/refusal";
import {
  useDeviceBlocked,
  useThisDevice,
} from "@/features/devices/this-device";

import { shopDatabase } from "../this-shop";
import { listenForAsks } from "./asks";
import { heardInTheBackground } from "./page-place";
import { syncShop, type SyncAsk } from "./sync";

/** How often an open app syncs while online (03 §6.5, a default): the office's changes reach the counter
 * within half a minute, and the server hears from each open tab as often. Each tab keeps its own ticks:
 * the lock puts two tabs in turn but doesn't merge them, so a laptop with two tabs open syncs twice as
 * often (a note for the sync health page, SYNC-14). */
export const SYNC_EVERY = 30_000;

/** How long after a save the sync goes (03 §6.5): soon enough that a record has most likely left before
 * the laptop is closed, and saves made close together go in one push. */
export const AFTER_A_SAVE = 2_000;

/**
 * What a failed sync leaves. Every failure waits for the next moment, which tries again from where the
 * last one stopped. The server's answers and a dropped network are part of a shop's day: a block or a
 * "not registered" is kept already (answer.ts), and the rest pass. Anything else is no answer of the
 * server's: an app older than the server (AppTooOld, which SYNC-13 turns into an update), a push the
 * server refused as broken (BrokenPush), or a bug. It would fail again at every moment with no one the
 * wiser, so it goes to the console, where a developer looking at a laptop that stopped syncing finds it.
 */
export function reportSyncFailure(error: unknown): void {
  if (error instanceof ApiRefusal || error instanceof NoConnection) return;
  console.error("sync failed", error);
}

/** One sync of a shop, as sync.ts runs it. Tests hand in their own, to count the moments. */
type Sync = (shopId: string, ask?: SyncAsk) => Promise<void>;

/**
 * Starts the shop's moments: a sync now, then at each moment after, until the returned function stops
 * them all. `sync` is replaced only by tests.
 */
export function startSyncTriggers(
  shopId: string,
  sync: Sync = syncShop,
): () => void {
  const run = (ask?: SyncAsk) => {
    if (!navigator.onLine) return;
    sync(shopId, ask).catch(reportSyncFailure);
  };

  // As the app opens, or as this laptop's device becomes known, or unblocked (useSyncTriggers).
  run();

  const networkBack = () => run();
  window.addEventListener("online", networkBack);

  const every = setInterval(run, SYNC_EVERY);

  // 2 s after a save. The first save starts the wait, and a save during it doesn't start it again: a busy
  // counter saving every second still sends every 2 s, never waiting for a quiet moment that doesn't come.
  let soon: ReturnType<typeof setTimeout> | undefined;
  const stopListening = listenForAsks((kind) => {
    if (kind === "send_now") {
      run({ sendNow: true });
      return;
    }
    if (soon !== undefined) return;
    soon = setTimeout(() => {
      soon = undefined;
      run();
    }, AFTER_A_SAVE);
  });

  return () => {
    window.removeEventListener("online", networkBack);
    clearInterval(every);
    clearTimeout(soon);
    stopListening();
  };
}

/**
 * Runs this laptop's moments while it is a working device of a shop: none while it isn't registered, as
 * there is no shop to sync, and none while it is blocked, as the server would refuse each. Its device
 * becoming known (a manager's yes) or unblocked starts them again, with a sync at once.
 */
export function useSyncTriggers(): void {
  const shopId = useThisDevice()?.shop.id;
  const blocked = useDeviceBlocked();
  useEffect(() => {
    if (shopId === undefined || blocked) return;
    // A block the service worker heard while the app was closed (SYNC-16) is taken as the app opens,
    // before any moment and with no network too: kept, it makes `blocked` true, and this stops again.
    heardInTheBackground(shopDatabase(shopId)).catch(reportSyncFailure);
    return startSyncTriggers(shopId);
  }, [shopId, blocked]);
}

/** This laptop's moments. Shows nothing; the root layout puts it on every page. */
export function SyncTriggers() {
  useSyncTriggers();
  return null;
}
