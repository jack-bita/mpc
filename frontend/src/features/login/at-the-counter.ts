// at-the-counter.ts — who is logged in at this laptop, as the counter screens read it (SYNC-11, 03 §5.9). It
// owns the counter's note of that person, and a counter screen's ask to log them out.
//
// The home page knows who is here: `me` from the server, or a local session the laptop let in with no
// network (at-the-device.tsx, offline-session.ts). A counter screen may not ask the server (rule 5,
// ADR-0019), so the home page writes a note here as each person arrives, and takes it away as they go.
// Every counter screen reads that note, online or offline alike: a clock-in names its maker by it.
//
// In this tab's memory only, as a local session is (Jack, SYNC-10): a reload, a crash or a closed tab
// throws it away, and the counter sends the person back to the home page, where `me` brings an online
// person back at once and an offline one types the PIN again. Nothing of it is written down, so nothing
// of it can be found later.
//
// It holds only while the laptop's copy still lets the person in: a sync that brings their suspension, a
// new PIN or their leaving takes it away (X2, 03 §5.9), and so does a block of the laptop, or a laptop
// forgotten or paired again. A counter screen never calls the server, so the server's own end of a session
// would never reach it: the laptop's copy is the only news it gets.
//
// Toka on a counter screen: the logout calls the server, so it stays with the home page (UI-4's note).
// The screen asks here (askToLeave): the person is hidden at once, for every screen, and the home page,
// which the screen opens next, logs them out and says it has heard (leaveHeard). The note keeps how they
// came in, by the server or by the laptop's own check, so the home page knows what to end even when it
// can't ask `me`: the store forgets an answer no screen read for 5 minutes, and the network may be gone.
// A server's session then gets its logout all the same, sent again until the server hears it.
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

/** How the person came in: by the server's session (a PIN the server said yes to, or a password), or by
 * the laptop's own check, a local session (SYNC-10). Each ends its own way. */
export type CameInBy = "server" | "laptop";

/** Who is here, as the home page last said. */
export interface CounterNote {
  staffId: string;
  by: CameInBy;
  /** Their PIN's time on the laptop's copy as they arrived: a new PIN since takes the note away. */
  pinChangedAt: string | null;
  /** How long the counter may sit untouched before it logs them out: `me`'s minutes, or offline the
   * shop's rule on the laptop, as the home page's own idle lock counts them. */
  idleMinutes: number;
  /** The device they arrived on, as the laptop's saved copy named it then. */
  deviceId: string | undefined;
}

/** Whom a counter screen asked to log out, and how they came in, so the home page ends the right session. */
export interface LeaveAsk {
  staffId: string;
  by: CameInBy;
}

/** The person at the counter: their row on the laptop now (a new nickname shows at once), and the
 * minutes the counter's idle lock keeps. */
export interface PersonAtCounter {
  row: StaffRow;
  idleMinutes: number;
}

let note: CounterNote | null = null;
// Whom a counter screen asked to log out, until the home page has heard. Apart from the note: the note
// goes at the press, so the person is hidden at once, and this stays until the logout.
let leaving: LeaveAsk | null = null;
const listeners = new Set<() => void>();
// The watch on the laptop's saved copy while a note lasts.
let stopWatching: (() => void) | null = null;

function tellEveryScreen(): void {
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function takeNoteAway(): void {
  stopWatching?.();
  stopWatching = null;
  note = null;
}

/** The home page: this person is here now, came in this way, and the counter locks after these minutes
 * untouched. */
export function arriveAtCounter(
  person: StaffRow,
  idleMinutes: number,
  by: CameInBy,
): void {
  // The same person again, as the home page draws each time: nothing changes, and no screen redraws.
  if (
    note?.staffId === person.id &&
    note.by === by &&
    note.pinChangedAt === person.pin_changed_at &&
    note.idleMinutes === idleMinutes
  )
    return;
  takeNoteAway();
  note = {
    staffId: person.id,
    by,
    pinChangedAt: person.pin_changed_at,
    idleMinutes,
    deviceId: savedDevice()?.id,
  };
  // Blocked, forgotten (its key opens no device), or paired again as another device: the note goes. The
  // block's lock covers every page, so no home page is on show to take it away, and an unblock in this
  // same tab would open the counter on the person with no PIN typed. A copy saved again unchanged tells
  // nobody, and a laptop renamed keeps its id, so the device check every few minutes takes nothing away.
  stopWatching = watchThisDevice(() => {
    if (note === null) return;
    if (savedBlocked() || savedDevice()?.id !== note.deviceId)
      nobodyAtCounter();
  });
  tellEveryScreen();
}

/** The home page: nobody is here. Also the note's own end, once the laptop no longer lets them in. */
export function nobodyAtCounter(): void {
  if (note === null) return;
  takeNoteAway();
  tellEveryScreen();
}

/** A counter screen's Toka, Badilisha mtu or idle lock: the person is hidden at once from every screen,
 * and the home page, opened next, logs them out. Nobody here, nothing to ask. */
export function askToLeave(): void {
  if (note === null) return;
  leaving = { staffId: note.staffId, by: note.by };
  takeNoteAway();
  tellEveryScreen();
}

/** The home page has heard the ask: it logged the person out, or they weren't here any more. */
export function leaveHeard(): void {
  if (leaving === null) return;
  leaving = null;
  tellEveryScreen();
}

/** The note, or null for nobody. useSyncExternalStore: React's way to read something kept outside React.
 * The build has no browser, so it builds as nobody. */
export function useAtTheCounter(): CounterNote | null {
  return useSyncExternalStore(
    subscribe,
    () => note,
    () => null,
  );
}

/** Whom a counter screen asked to log out, and how they came in, not yet heard by the home page; null for
 * none. */
export function useLeaveAsked(): LeaveAsk | null {
  return useSyncExternalStore(
    subscribe,
    () => leaving,
    () => null,
  );
}

/**
 * The person at the counter, as the laptop's copy has them now: null for nobody, undefined while their
 * row is still being read. Two answers, as a screen must tell them apart: nobody sends it back to the
 * name tiles, still reading only waits. Read as one, a screen would send Asha away while her row is on
 * its way.
 *
 * Takes the note away by itself once that copy no longer lets them in: their row gone (they left, or
 * were switched off), suspended (X2), or a new PIN since they arrived.
 */
export function usePersonAtCounter(): PersonAtCounter | null | undefined {
  const current = useAtTheCounter();
  const db = useShopDatabase();
  // Read live, with the note it was read for: right after a new person arrives, the hook still hands back
  // the read made for the last one, which must neither show them nor end the new note.
  const read = useLiveQuery(async () => {
    if (current === null || db === null) return { current, row: undefined };
    return { current, row: await db.staff.get(current.staffId) };
  }, [db, current]);

  const readNow = read !== undefined && read.current === current;
  const row = readNow ? read.row : undefined;
  const stillIn =
    current !== null &&
    row !== undefined &&
    row.status === "active" &&
    row.pin_changed_at === current.pinChangedAt;

  useEffect(() => {
    // Only on a read made for this very note, and only while it is still the note: one that went
    // meanwhile, or was replaced by the next person's, is not this read's to end.
    if (current !== null && readNow && !stillIn && note === current)
      nobodyAtCounter();
  }, [current, readNow, stillIn]);

  if (current === null) return null;
  if (!readNow) return undefined;
  // `row !== undefined` again for TypeScript only: stillIn already says so, but a boolean held apart
  // doesn't narrow the type.
  return stillIn && row !== undefined
    ? { row, idleMinutes: current.idleMinutes }
    : null;
}
