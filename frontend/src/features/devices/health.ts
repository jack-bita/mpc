// health.ts — the rules behind *Hali ya vifaa*, the device health page (SYNC-14, 03 §5.17): whether a
// device has synced today, what its clock error says, and how long each offline period lasted. Pure
// functions of what the server sent and of now, so each is tested on its own (health.test.ts) and the
// screen (device-health.tsx) only lays them out.
//
// Every time a laptop reported about itself is by its own clock (02: DeviceOutage), so a period may end
// before it starts: it is told apart here, never shown as a negative length. The last sync is the
// server's own clock, so "today" is the shop's today, in its zone.
import type { components } from "@/api/schema";
import { shopToday } from "@/offline/rules";

type Outage = components["schemas"]["DeviceOutage"];

/** How far a laptop's clock may be from the server's and still count as right: 2 minutes, the slack a
 * clock-in's time check allows too (CLOCK_SLACK, apps/staffpay/calculations.py, 02 §12). A clock within
 * it never makes a clock-in wait for review, so the page has nothing to ask of the manager. */
export const CLOCK_SLACK_SECONDS = 120;

const MINUTE = 60_000;

/**
 * Whether the device's last sync was on the shop's today, in its own zone: a laptop that last synced at
 * 23:50 yesterday in Arusha has not synced today, though UTC may still say so. Never synced is not today.
 */
export function syncedToday(
  lastSyncedAt: string | null,
  timezone: string,
  now: number,
): boolean {
  if (lastSyncedAt === null) return false;
  return (
    shopToday(timezone, Date.parse(lastSyncedAt)) === shopToday(timezone, now)
  );
}

/** What a laptop's clock error says: not known before its first push; right within the slack; else ahead
 * or behind, in whole minutes (a clock 6 min 20 s slow is "6 minutes behind"). */
export type ClockState =
  | { kind: "unknown" }
  | { kind: "right" }
  | { kind: "ahead" | "behind"; minutes: number };

export function clockState(errorSeconds: number | null): ClockState {
  if (errorSeconds === null) return { kind: "unknown" };
  if (Math.abs(errorSeconds) <= CLOCK_SLACK_SECONDS) return { kind: "right" };
  // The laptop's clock minus the server's (DeviceHealth.clock_error_seconds): above 0 it runs ahead.
  return {
    kind: errorSeconds > 0 ? "ahead" : "behind",
    minutes: Math.round(Math.abs(errorSeconds) / 60),
  };
}

/** A length of time as the page says it: under a minute, or hours and minutes, rounded to the minute. */
export type Duration =
  { kind: "underAMinute" } | { kind: "time"; hours: number; minutes: number };

export function duration(milliseconds: number): Duration {
  if (milliseconds < MINUTE) return { kind: "underAMinute" };
  const minutes = Math.round(milliseconds / MINUTE);
  return {
    kind: "time",
    hours: Math.floor(minutes / 60),
    minutes: minutes % 60,
  };
}

/** How long a period lasted, in milliseconds, or null when it ends before it starts: the laptop's clock
 * was put back during it, and no length can be told. */
export function outageLength(outage: Outage): number | null {
  const length = Date.parse(outage.ended_at) - Date.parse(outage.started_at);
  return length < 0 ? null : length;
}

/** The week's periods in short: how many, and how long in all, of those whose length can be told; null
 * when none can, so the page never calls an unknown length "under a minute". */
export function weekOfOutages(outages: readonly Outage[]): {
  count: number;
  total: number | null;
} {
  let total: number | null = null;
  for (const outage of outages) {
    const length = outageLength(outage);
    if (length !== null) total = (total ?? 0) + length;
  }
  return { count: outages.length, total };
}
