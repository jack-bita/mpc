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
//
// Honest limits, beside 03 §5.9's (a check on a stolen laptop can be guessed, by someone with the skills):
// - The lock reads the laptop's clock. Someone who moves it forward shortens a lock; back, lengthens it.
// - Anyone who can open the browser's developer tools on the laptop can write a check of their own, for
//   any person, and log in as them offline. A PIN stops coworkers using each other's names, not a thief;
//   what they do offline still reaches the server under that name, with the laptop's own.

import type { components } from "@/api/schema";

import type { PinCheckRow, ShopDatabase } from "./db";

type StaffRecord = components["schemas"]["StaffRecord"];

// The server's three numbers, the same here (apps/people/pins.py): a lock comes after five wrong PINs,
// lasts a minute the first time, and twice as long each time after, never more than an hour.
export const PIN_TRIES = 5;
export const FIRST_LOCK_MINUTES = 1;
export const LONGEST_LOCK_MINUTES = 60;

/** How many turns of the blender a new check is made with: OWASP's number for PBKDF2 with SHA-256.
 * Saved in each check, so a later app that raises it still reads the checks made before. */
export const PIN_ITERATIONS = 600_000;

const MINUTE = 60_000;

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
 * their staff row's pin_changed_at. Replaces any check before it, and lifts their lock here, as the
 * server's right PIN lifts its own. Saves nothing for someone with no staff row on the laptop (one never
 * filled yet). `iterations` is for tests only, which pay for fewer turns.
 */
export async function rememberPin(
  db: ShopDatabase,
  staffId: string,
  pin: string,
  iterations: number = PIN_ITERATIONS,
): Promise<void> {
  // The PIN's time is read before the blender runs, so the check is tied to the PIN the laptop knew of
  // when the server said yes. A laptop not filled yet has no row: no time to tie a check to.
  const person = await db.staff.get(staffId);
  if (person === undefined) return;

  // A new salt for every check, made here: the same PIN gives another check for another person, at
  // another login, on another laptop.
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const check = await blend(pin, salt, iterations);

  // Written in a transaction of its own, after the blender: Dexie ends a transaction that waits on
  // anything but the database, and the blender takes a third of a second.
  await db.transaction("rw", [db.staff, db.pin_checks], async () => {
    // A sync while the blender ran brought her a new PIN: the one typed may be the old one, so it is
    // tied to nothing. She logs in online once more.
    const still = await db.staff.get(staffId);
    if (still?.pin_changed_at !== person.pin_changed_at) return;
    await db.pin_checks.put({
      staff_id: staffId,
      salt: toHex(salt),
      check,
      iterations,
      pin_changed_at: person.pin_changed_at,
      wrong_tries: 0,
      next_lock_minutes: FIRST_LOCK_MINUTES,
      locked_until: null,
    });
  });
}

/**
 * Offline: is this the person's PIN, on this laptop, at `now` (the laptop's clock, in ms)? Resolves with
 * their staff row, or throws PinRefused. In the server's order (check_pin, apps/people/services.py): who
 * they are, then the lock, then the try counted, and only then the slow check.
 */
export async function checkPinOffline(
  db: ShopDatabase,
  staffId: string,
  pin: string,
  now: number = Date.now(),
): Promise<StaffRecord> {
  // 1. The try is counted first, and kept even if the check then fails: a tab closed in the middle of
  //    the blender, again and again, would otherwise try every PIN for free (the server's rule, AUTH-4).
  const counted = await db.transaction("rw", [db.staff, db.pin_checks], () =>
    countTry(db, staffId, now),
  );
  if (counted instanceof PinRefused) throw counted;

  // 2. The slow check, outside any transaction, for the reason rememberPin gives. A plain comparison:
  //    the row it compares with can be read on the laptop anyway, so its timing tells nobody more.
  const typed = await blend(pin, fromHex(counted.salt), counted.iterations);
  if (typed === counted.check) {
    const letIn = await db.transaction("rw", [db.staff, db.pin_checks], () =>
      lift(db, counted),
    );
    if (letIn instanceof PinRefused) throw letIn;
    return letIn;
  }

  // The fifth wrong try started a lock just now: she is told so at once, with how long.
  if (counted.locked_until !== null && now < counted.locked_until)
    throw locked(counted.locked_until, now);
  throw new PinRefused("pin.wrong");
}

// Inside a transaction. A refusal is returned, not thrown: a throw would undo the transaction, and with
// it the try just counted, or the outdated check just dropped.
async function countTry(
  db: ShopDatabase,
  staffId: string,
  now: number,
): Promise<PinCheckRow | PinRefused> {
  // Not on the laptop: never here, or taken off by a pull, as someone who left or was switched off.
  const person = await db.staff.get(staffId);
  if (person === undefined) return new PinRefused("pin.offline_first");
  // X2: suspended, as the last sync said. Told so with no check, and the try isn't counted, so her wrong
  // tries lock nothing for when she is back (the server's order, pin_login).
  if (person.status !== "active") return new PinRefused("staff.suspended");

  const held = await db.pin_checks.get(staffId);
  if (held === undefined) return new PinRefused("pin.offline_first");
  // A check made for another PIN than her row's: never used, and dropped, however the row came to
  // differ (dropOutdatedChecks drops it at the pull already).
  if (held.pin_changed_at !== person.pin_changed_at) {
    await db.pin_checks.delete(staffId);
    return new PinRefused("pin.offline_first");
  }

  // Locked: refused with no check, so a flood of tries costs the laptop nothing.
  if (held.locked_until !== null && now < held.locked_until)
    return locked(held.locked_until, now);

  // This try, counted. The fifth starts a lock, and the next lock will last twice as long.
  const tried: PinCheckRow = { ...held, wrong_tries: held.wrong_tries + 1 };
  if (tried.wrong_tries === PIN_TRIES) {
    tried.wrong_tries = 0;
    tried.locked_until = now + held.next_lock_minutes * MINUTE;
    tried.next_lock_minutes = Math.min(
      held.next_lock_minutes * 2,
      LONGEST_LOCK_MINUTES,
    );
  }
  await db.pin_checks.put(tried);
  return tried;
}

// Inside a transaction, after a right PIN: the count and the lock start again, as the server's do. Read
// again first: while the blender ran, a sync may have taken her off, suspended her, or brought a new PIN
// that dropped this check.
async function lift(
  db: ShopDatabase,
  counted: PinCheckRow,
): Promise<StaffRecord | PinRefused> {
  const person = await db.staff.get(counted.staff_id);
  const held = await db.pin_checks.get(counted.staff_id);
  if (person === undefined || held?.salt !== counted.salt)
    return new PinRefused("pin.offline_first");
  if (person.status !== "active") return new PinRefused("staff.suspended");
  await db.pin_checks.put({
    ...held,
    wrong_tries: 0,
    next_lock_minutes: FIRST_LOCK_MINUTES,
    locked_until: null,
  });
  return person;
}

/** Drops each check its person's staff row no longer matches: a new PIN, a PIN taken away, or someone
 * the laptop no longer has (who left, or was switched off). A suspended person keeps theirs: suspending
 * changes no PIN, and the check above refuses them while it lasts. Runs inside a pull's or a bootstrap's
 * transaction, which must include pin_checks and staff, so the staff rows and their checks change
 * together. */
export async function dropOutdatedChecks(db: ShopDatabase): Promise<void> {
  // A shop has a handful of people: reading every check is cheaper than finding which ones changed.
  const outdated: string[] = [];
  for (const held of await db.pin_checks.toArray()) {
    const person = await db.staff.get(held.staff_id);
    if (person?.pin_changed_at !== held.pin_changed_at)
      outdated.push(held.staff_id);
  }
  await db.pin_checks.bulkDelete(outdated);
}

// pin.locked, with the wait in whole seconds, rounded up, as the server says it: never "0 seconds"
// while some are left.
function locked(until: number, now: number): PinRefused {
  return new PinRefused("pin.locked", {
    wait: Math.ceil((until - now) / 1000),
  });
}

// The PIN through the blender: PBKDF2 with SHA-256, `iterations` turns, with this salt; 32 bytes out,
// as hex. The PIN goes in as a key the browser never lets anyone read back (extractable: false).
async function blend(
  pin: string,
  salt: Uint8Array<ArrayBuffer>,
  iterations: number,
): Promise<string> {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(pin),
    "PBKDF2",
    false,
    ["deriveBits"],
  );
  const bits = await crypto.subtle.deriveBits(
    { name: "PBKDF2", hash: "SHA-256", salt, iterations },
    key,
    256,
  );
  return toHex(new Uint8Array(bits));
}

// Bytes as text, two letters 0–9 a–f each, so a row in the database holds plain text.
function toHex(bytes: Uint8Array): string {
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join(
    "",
  );
}

// The saved salt, back to bytes for the blender.
function fromHex(hex: string): Uint8Array<ArrayBuffer> {
  return Uint8Array.from(hex.match(/../g) ?? [], (pair) => parseInt(pair, 16));
}
