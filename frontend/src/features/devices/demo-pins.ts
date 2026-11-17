// demo-pins.ts — the demo sellers' PINs, as one tap on Jaribu demo handed them over (OPS-3, demo.ts),
// kept on the laptop for the PIN screen to show under their tiles (staff-picker.tsx).
//
// Kept in localStorage, by staff id, so the tiles show them with no network too (SYNC-10). They are no
// secret: they open only the demo's fake shop, made again every day, and the README prints them. A staff
// id is a UUIDv7, never shared by two shops, so a PIN kept from yesterday's demo, whose people the daily
// reset made again with new ids, matches no tile, and no real shop's tile ever shows one.
//
// This file never calls the server, so any screen may read it, as this-device.ts.

/** The browser's key for the kept PINs. "mpc." keeps it apart, as "mpc.device" does. */
export const DEMO_PINS_KEY = "mpc.demo-pins";

/** The PIN kept for this staff member, or undefined: none kept, or none of theirs. */
export function demoPin(staffId: string): string | undefined {
  return keptPins()[staffId];
}

/** Keeps the PINs one tap handed over, in place of any kept before. */
export function savePins(
  pins: readonly { staff_id: string; pin: string }[],
): void {
  const byStaff = Object.fromEntries(pins.map((p) => [p.staff_id, p.pin]));
  try {
    window.localStorage.setItem(DEMO_PINS_KEY, JSON.stringify(byStaff));
  } catch {
    // Storage refused (a browser set to block it): the tiles show no PIN, and the README still has them.
  }
}

// The kept PINs, by staff id. Anything we can't read, written by hand or by another version of the app,
// reads as none: a tile with no PIN under it is the worst that follows.
function keptPins(): Record<string, string> {
  try {
    const value: unknown = JSON.parse(
      window.localStorage.getItem(DEMO_PINS_KEY) ?? "{}",
    );
    if (typeof value !== "object" || value === null || Array.isArray(value))
      return {};
    return Object.fromEntries(
      Object.entries(value).filter(
        (entry): entry is [string, string] => typeof entry[1] === "string",
      ),
    );
  } catch {
    return {};
  }
}
