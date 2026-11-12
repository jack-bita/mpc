// pin.ts — a PIN checked on the laptop itself, for a login with no network (SYNC-10, 03 §5.9).
//
// The server never sends a PIN or its hash (nothing secret syncs). So the laptop makes its own check
// value, at each online PIN login the server said yes to: PBKDF2, the browser's slow blender (WebCrypto),
// over the PIN and a fresh random salt, saved in pin_checks, one row per person (db.ts). Offline, the PIN
// typed goes through the same blender with the same salt: the same text means the same PIN.
//
// It owns the three rules of an offline PIN:
//   remember   after the server's yes, a fresh check of that PIN (rememberPin)
//   check      offline, the PIN against that check, with the lock: five wrong PINs lock the person on
//              this laptop for a minute, then twice as long each time, up to an hour, the server's own
//              numbers (apps/people/pins.py); a try is counted before its check (checkPinOffline)
//   forget     a check the person's staff row no longer matches: a new PIN, or someone who left
//              (dropOutdatedChecks, at each pull and bootstrap)

import type { components } from "@/api/schema";

import type { ShopDatabase } from "./db";

type StaffRecord = components["schemas"]["StaffRecord"];

// The server's three numbers, the same here (apps/people/pins.py): a lock comes after five wrong PINs,
// lasts a minute the first time, and twice as long each time after, never more than an hour.
export const PIN_TRIES = 5;
export const FIRST_LOCK_MINUTES = 1;
export const LONGEST_LOCK_MINUTES = 60;

/** How many turns of the blender a new check is made with: OWASP's number for PBKDF2 with SHA-256.
 * Saved in each check, so a later app that raises it still reads the checks made before. */
export const PIN_ITERATIONS = 600_000;

/** Why the laptop said no. The server's own codes where it would say the same, so both say it in the
 * same words; and one only the laptop says. */
export type PinRefusalCode =
  /** Not this person's PIN. */
  | "pin.wrong"
  /** Five wrong PINs: locked here for `wait` seconds more. */
  | "pin.locked"
  /** Suspended on the server, as the laptop's last sync said: no check is made. */
  | "staff.suspended"
  /** No check of their PIN on this laptop: never logged in here online, or their PIN changed since. */
  | "pin.offline_first";

/** The laptop's no to an offline PIN login. */
export class PinRefused extends Error {
  constructor(
    readonly code: PinRefusalCode,
    /** `wait`, in whole seconds, for pin.locked, as the server sends it. */
    readonly params: { wait?: number } = {},
  ) {
    super(code);
    this.name = "PinRefused";
  }
}

/**
 * After the server's yes to this PIN: saves a fresh check of it for this person, on this laptop, with
 * their staff row's pin_changed_at. Replaces any check before it, and lifts their lock here. Saves
 * nothing for someone with no staff row on the laptop (one never filled yet). `iterations` is for tests
 * only, which pay for fewer turns.
 */
export async function rememberPin(
  db: ShopDatabase,
  staffId: string,
  pin: string,
  iterations: number = PIN_ITERATIONS,
): Promise<void> {
  notWrittenYet(db, staffId, pin, iterations);
}

/**
 * Offline: is this the person's PIN, on this laptop, at `now` (the laptop's clock, in ms)? Resolves with
 * their staff row, or throws PinRefused.
 */
export async function checkPinOffline(
  db: ShopDatabase,
  staffId: string,
  pin: string,
  now: number = Date.now(),
): Promise<StaffRecord> {
  return notWrittenYet(db, staffId, pin, now);
}

/** Drops each check its person's staff row no longer matches. Runs inside a pull's or a bootstrap's
 * transaction, which must include pin_checks and staff. */
export async function dropOutdatedChecks(db: ShopDatabase): Promise<void> {
  notWrittenYet(db);
}

// Step 1 of SYNC-10: the tests come first, and fail here until the rules are written.
function notWrittenYet(...given: unknown[]): never {
  throw new Error(`Not written yet (${given.length} values given).`);
}
