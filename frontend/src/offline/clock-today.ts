// clock-today.ts — the clock-ins and clock-outs saved on this laptop today, read live, for the Mahudhurio
// screen (SYNC-11, 02 §12): whether the person here is in, and who is. It owns what a clock document's
// payload holds on the laptop, and which day is today for the taps.
//
// Today is the shop's date, in the shop's own time zone (mpc.device's shop.timezone), never the laptop's
// zone, which may be set to anything. By the laptop's own clock, not put right by the server's offset as a
// rule's day is (reference.ts): a tap is written with the laptop's clock (client_time), so a screen that
// worked out today on another clock could leave a tap just made out of today's list. The server decides
// the time it trusts, and flags a clock that moved (ATT-1's time check); this only shows what the laptop
// wrote.
//
// Taps are found by the documents drawer's [type+client_time] key: the clock documents in a window of UTC
// times that holds the whole day in any zone, then only those whose time falls on today in the shop's
// zone. No zone maths of our own: Intl works out each tap's date, as it does for the rules (shopToday).
//
// Only this laptop's taps: a clock-in made on the Vyakula laptop is in its own database, and reaches the
// server from there (Jack, SYNC-11).
import { useLiveQuery } from "dexie-react-hooks";
import { useEffect, useState } from "react";

import { useThisDevice } from "@/features/devices/this-device";

import type { DocumentRow } from "./db";
import { shopToday } from "./rules";
import { useShopDatabase } from "./this-shop";

/** A clock document's type, as the server names it (apps/sync/document_types.py, ATT-1). */
export const CLOCK = "clock";
/** Its payload's shape version: ClockShape, apps/staffpay/documents.py. */
export const CLOCK_VERSION = 1;

export type ClockKind = "in" | "out";

/** A clock document's payload: what was tapped, and the last time the server had told the laptop. */
export interface ClockPayload {
  kind: ClockKind;
  last_server_time: string;
}

/** One tap, as the screen reads it. */
export interface Tap {
  id: string;
  staffId: string;
  kind: ClockKind;
  /** The laptop's clock at the tap, with its zone (`Z`). */
  at: string;
}

/** Today's taps, and the day they are of. */
export interface TodaysTaps {
  day: string;
  taps: Tap[];
}

/** How often today is worked out again: a screen open across midnight turns to the new day within a
 * minute, with nothing saved or pulled. A live query runs again when its rows change, not when the clock
 * passes midnight (SYNC-7's note). */
export const DAY_CHECK_EVERY = 60 * 1000;

const HOUR = 60 * 60 * 1000;
// The zones go from 12 hours behind UTC to 14 ahead (Kiritimati): 14 on both sides holds a day anywhere.
const WIDEST_ZONE = 14 * HOUR;

/** The UTC times, as ISO texts, between which every moment of `day` ("2026-11-13") falls, in any zone.
 * ISO texts with `Z` sort as the times they name, so the drawer's key can search between them. */
export function dayWindow(day: string): [string, string] {
  const midnight = Date.parse(`${day}T00:00:00.000Z`);
  return [
    new Date(midnight - WIDEST_ZONE).toISOString(),
    new Date(midnight + 24 * HOUR + WIDEST_ZONE).toISOString(),
  ];
}

function isClockKind(kind: unknown): kind is ClockKind {
  return kind === "in" || kind === "out";
}

/**
 * Of these clock documents, the taps made on `day` in `timezone`, in the order given (the drawer's, by
 * time). One whose payload names no kind of tap, as a damaged row or another app's could, is left out:
 * read as a tap, it would show someone in or out who never tapped.
 */
export function tapsOnDay(
  documents: readonly DocumentRow[],
  timezone: string,
  day: string,
): Tap[] {
  const taps: Tap[] = [];
  for (const document of documents) {
    const kind = (document.payload as { kind?: unknown } | null)?.kind;
    if (!isClockKind(kind)) continue;
    if (shopToday(timezone, Date.parse(document.client_time)) !== day) continue;
    taps.push({
      id: document.id,
      staffId: document.created_by,
      kind,
      at: document.client_time,
    });
  }
  return taps;
}

/** One person's day so far on this laptop, for today's list. */
export interface PersonsDay {
  staffId: string;
  /** Their first clock-in today: when they came. Null for a clock-out with none before it. */
  cameAt: string | null;
  /** Their last clock-out, while they are out: null while they are in, back from lunch too. */
  leftAt: string | null;
}

/**
 * Of today's taps, in time order, each person once, in the order they first tapped: when they came, and
 * when they left if they are out now. The list a shop's sign-in sheet would show; the day's hours, and
 * whether someone was late, are the server's to work out (AttendanceDay, ATT cards).
 */
export function peopleToday(taps: readonly Tap[]): PersonsDay[] {
  const days = new Map<string, PersonsDay>();
  for (const tap of taps) {
    let day = days.get(tap.staffId);
    if (day === undefined) {
      day = { staffId: tap.staffId, cameAt: null, leftAt: null };
      days.set(tap.staffId, day);
    }
    if (tap.kind === "in") {
      day.cameAt ??= tap.at;
      // Back in after a clock-out, as after lunch: here again, so no leaving time.
      day.leftAt = null;
    } else day.leftAt = tap.at;
  }
  // A Map gives its entries in the order they were added: the order each person first tapped.
  return [...days.values()];
}

/** Today, by the laptop's clock, in the shop's zone ("2026-11-13"); undefined on a laptop with no shop.
 * Worked out again every minute, so it turns at midnight by itself. */
export function useClockDay(): string | undefined {
  const timezone = useThisDevice()?.shop.timezone;
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const every = setInterval(() => setNow(Date.now()), DAY_CHECK_EVERY);
    return () => clearInterval(every);
  }, []);
  return timezone === undefined ? undefined : shopToday(timezone, now);
}

/** Today's taps on this laptop, everyone's, by time, read live: a tap saved shows at once. Undefined
 * while the first read runs, or on a laptop with no shop. */
export function useTodaysTaps(): TodaysTaps | undefined {
  const db = useShopDatabase();
  const timezone = useThisDevice()?.shop.timezone;
  const day = useClockDay();
  return useLiveQuery(async () => {
    if (db === null || timezone === undefined || day === undefined)
      return undefined;
    const [from, to] = dayWindow(day);
    const documents = await db.documents
      .where("[type+client_time]")
      .between([CLOCK, from], [CLOCK, to], true, true)
      .toArray();
    return { day, taps: tapsOnDay(documents, timezone, day) };
  }, [db, timezone, day]);
}
