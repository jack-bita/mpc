// demo-pins.ts — the demo's public ways in, as one tap on Jaribu demo handed them over (demo.ts): the
// sellers' PINs (OPS-3), for the PIN screen to show under their tiles, and the manager's login (OPS-13),
// for his tile, which opens the password login with both boxes filled (staff-picker.tsx, password-login.tsx).
//
// Kept in localStorage, by staff id, so the tiles show them with no network too (SYNC-10). They are no
// secret: they open only the demo's fake shop, made again every day, and the README prints them. The
// password is the seed's public one, never a real one: a real password never leaves the server. A staff id
// is a UUIDv7, never shared by two shops, so a PIN or a login kept from yesterday's demo, whose people the
// daily reset made again with new ids, matches no tile, and no real shop's tile ever shows one.
//
// The PINs and the logins each have a key of their own: a version of the app from before OPS-13 still
// reads the PINs as it did.
//
// This file never calls the server, so any screen may read it, as this-device.ts.

/** The browser's key for the kept PINs. "mpc." keeps it apart, as "mpc.device" does. */
export const DEMO_PINS_KEY = "mpc.demo-pins";

/** The browser's key for the kept logins. */
export const DEMO_LOGINS_KEY = "mpc.demo-logins";

/** A login the tap handed over: what goes in the login page's two boxes. */
export interface DemoLogin {
  login: string;
  password: string;
}

/** The PIN kept for this staff member, or undefined: none kept, or none of theirs. */
export function demoPin(staffId: string): string | undefined {
  return keptPins()[staffId];
}

/** Keeps the PINs one tap handed over, in place of any kept before. */
export function savePins(
  pins: readonly { staff_id: string; pin: string }[],
): void {
  keep(DEMO_PINS_KEY, Object.fromEntries(pins.map((p) => [p.staff_id, p.pin])));
}

/** The login kept for this staff member, or undefined: none kept, or none of theirs. */
export function demoLogin(staffId: string): DemoLogin | undefined {
  return keptLogins()[staffId];
}

/** Keeps the logins one tap handed over, in place of any kept before. */
export function saveLogins(
  logins: readonly { staff_id: string; login: string; password: string }[],
): void {
  keep(
    DEMO_LOGINS_KEY,
    Object.fromEntries(
      logins.map((l) => [l.staff_id, { login: l.login, password: l.password }]),
    ),
  );
}

function keep(key: string, value: object): void {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Storage refused (a browser set to block it): the tiles show no PIN and no login, and the README still
    // has them.
  }
}

// The kept PINs, by staff id. Anything we can't read, written by hand or by another version of the app,
// reads as none: a tile with no PIN under it is the worst that follows.
function keptPins(): Record<string, string> {
  return Object.fromEntries(
    Object.entries(kept(DEMO_PINS_KEY)).filter(
      (entry): entry is [string, string] => typeof entry[1] === "string",
    ),
  );
}

// The kept logins, by staff id, each with both its strings, or it reads as none: a login with no password
// would fill one box, and lead nowhere.
function keptLogins(): Record<string, DemoLogin> {
  return Object.fromEntries(
    Object.entries(kept(DEMO_LOGINS_KEY)).filter(
      (entry): entry is [string, DemoLogin] => isLogin(entry[1]),
    ),
  );
}

function isLogin(value: unknown): value is DemoLogin {
  return (
    typeof value === "object" &&
    value !== null &&
    typeof (value as Partial<DemoLogin>).login === "string" &&
    typeof (value as Partial<DemoLogin>).password === "string"
  );
}

// What is kept under `key`, as an object, or an empty one for anything else.
function kept(key: string): Record<string, unknown> {
  try {
    const value: unknown = JSON.parse(window.localStorage.getItem(key) ?? "{}");
    if (typeof value !== "object" || value === null || Array.isArray(value))
      return {};
    return value as Record<string, unknown>;
  } catch {
    return {};
  }
}
