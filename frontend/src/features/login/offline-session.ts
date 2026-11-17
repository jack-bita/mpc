// offline-session.ts — who is logged in at this laptop by an offline PIN check: a local session (SYNC-10,
// 03 §5.9). It owns that session: its start, its end, and how long it holds.
//
// A server's session lives in a cookie, and the server keeps it. One made with no network has no server, so
// the laptop keeps it, in this tab's memory only (Jack, 12 Nov 2026): a reload, a crash or a closed tab ends
// it, and the person types their PIN again. Nothing of it is written down, so nothing of it can be copied
// or found later.
//
// It holds the person's id and the PIN time their check was made for, and it holds only while the laptop's
// copy still lets them in: a sync that brings their suspension, a new PIN, or their leaving ends it at once,
// as the server ends a session at the next click after the same (03 §5.9, what a session holds). So does a
// block of the laptop, or a laptop forgotten or paired again, as a server's session ends with its device.
//
// Selling uses the device's key, not a session, so a local session is all a counter screen needs, online
// too (SYNC-11 reads it). The office screens need the server's, and say so.
import { useLiveQuery } from "dexie-react-hooks";
import { useEffect, useSyncExternalStore } from "react";

import type { components } from "@/api/schema";
import {
  savedBlocked,
  savedDevice,
  watchThisDevice,
} from "@/features/devices/this-device";
import { useShopDatabase } from "@/offline/this-shop";

type StaffRow = components["schemas"]["StaffRecord"];

/** Who logged in here offline, the PIN time the laptop checked them against, and the device they logged
 * in on, as the laptop's saved copy named it then. */
export interface OfflineSession {
  staffId: string;
  pinChangedAt: string | null;
  deviceId: string | undefined;
}

let current: OfflineSession | null = null;
const listeners = new Set<() => void>();
// The watch on the laptop's saved copy while a session lasts.
let stopWatching: (() => void) | null = null;

function tellEveryScreen(): void {
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** After the laptop's own yes to a PIN (checkPinOffline): this person is here. */
export function startOfflineSession(person: StaffRow): void {
  stopWatching?.();
  current = {
    staffId: person.id,
    pinChangedAt: person.pin_changed_at,
    deviceId: savedDevice()?.id,
  };
  // Blocked, forgotten (its key opens no device), or paired again as another device: the session ends
  // there. The block's lock covers every page, so the home page isn't on show to end it, and an unblock in
  // this same tab would bring the person back with no PIN. A copy saved again unchanged tells nobody, and a
  // laptop renamed keeps its id, so the device check every few minutes ends nothing.
  stopWatching = watchThisDevice(() => {
    if (current === null) return;
    if (savedBlocked() || savedDevice()?.id !== current.deviceId)
      endOfflineSession();
  });
  tellEveryScreen();
}

/** Toka, Badilisha mtu, the idle lock, the laptop's copy no longer letting them in, or the laptop blocked. */
export function endOfflineSession(): void {
  stopWatching?.();
  stopWatching = null;
  if (current === null) return;
  current = null;
  tellEveryScreen();
}

/** The local session, or null for none. useSyncExternalStore: React's way to read something kept
 * outside React. The build has no browser, so it builds as nobody. */
export function useOfflineSession(): OfflineSession | null {
  return useSyncExternalStore(
    subscribe,
    () => current,
    () => null,
  );
}

/**
 * The person logged in here offline, as the laptop's copy has them now (a new nickname shows at once), or
 * undefined for nobody. Ends the session by itself once that copy no longer lets them in: their row gone
 * (they left, or were switched off), suspended (X2), or a new PIN since their check.
 */
export function useOfflinePerson(): StaffRow | undefined {
  const session = useOfflineSession();
  const db = useShopDatabase();
  // Read live, with the session it was read for: right after a new session starts, the hook still hands
  // back the read made for the last one, which must not end the new one.
  const read = useLiveQuery(async () => {
    if (session === null || db === null) return { session, row: undefined };
    return { session, row: await db.staff.get(session.staffId) };
  }, [db, session]);

  const readNow = read !== undefined && read.session === session;
  const row = readNow ? read.row : undefined;
  const stillIn =
    session !== null &&
    row !== undefined &&
    row.status === "active" &&
    row.pin_changed_at === session.pinChangedAt;

  useEffect(() => {
    // Only on a read made for this very session, so a session isn't ended before its row is read.
    if (session !== null && readNow && !stillIn) endOfflineSession();
  }, [session, readNow, stillIn]);

  return stillIn ? row : undefined;
}
