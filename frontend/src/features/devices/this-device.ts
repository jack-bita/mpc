// this-device.ts — which device this is, as the server last said: its name, its number, its shop and
// its home side, and whether it is blocked (UI-3, 03 §5.9, steps 3 and 4).
//
// Kept on the device (localStorage), so the top bar still names the shop with no network, and after a
// reload. The server is the one that knows: device-check.tsx asks it and saves the answer here. This
// file never calls the server itself, so any screen may read it, counter screens included: they will
// need the device's number for receipt numbers (D7), and they never import the API client (rule 5,
// ADR-0019).
//
// Nothing saved reads as "not registered": a new device, a phone that is only a manager's own, or a
// device whose saved copy was wiped. The next check puts it right if the server knows otherwise.
//
// A block is kept too, so the lock stays on through a reload with no network: a stolen laptop taken
// offline after it saw its block still shows nothing of the shop's work. Honest limit: one kept offline
// from before its block never hears of it, until its next request reaches the server (03 §5.9).
import { useSyncExternalStore } from "react";

/** This device, as the top bar and the screens need it. Our own shape, not the API's: a later change to
 * the API's answer changes device-check.tsx only, and a copy saved by an older app is checked on read. */
export interface ThisDevice {
  id: string;
  /** Its name on the manager's list, like "Laptop Dawa". */
  name: string;
  /** Its number in the shop, for receipt numbers (D7): never reused, never changed. */
  code: number;
  shop: { id: string; name: string; code: string };
  /** The side it mostly serves, which the counter screens open on. */
  homeSide: { id: string; code: string; name: string };
}

/** What the server last said: the device, if it ever said who it is, and whether it is blocked. A block
 * keeps the device, so the lock can say which device the manager must unblock. A device the app never
 * knew can still be blocked: its saved copy was wiped, and its key still works for the server. */
interface Standing {
  device: ThisDevice | null;
  blocked: boolean;
}

const NOT_REGISTERED: Standing = { device: null, blocked: false };

// The browser's key for the saved copy. "mpc." keeps it apart from anything else on the same address,
// as the language choice's "mpc.language" does.
export const DEVICE_STORAGE_KEY = "mpc.device";

// The last text read from storage, and what it meant. React asks for the saved copy on every draw, and
// wants the very same object back while nothing changed, or it draws again without end; reading JSON
// makes a new object each time. So it is read again only when the text itself changed.
let lastText: string | null = null;
let lastStanding: Standing = NOT_REGISTERED;

function savedStanding(): Standing {
  let text: string | null;
  try {
    text = window.localStorage.getItem(DEVICE_STORAGE_KEY);
  } catch {
    // A browser set to block every site's storage refuses even to read it. The device then knows
    // itself only until the page closes: such a browser can't run the counter anyway (language.ts).
    return NOT_REGISTERED;
  }
  if (text !== lastText) {
    lastText = text;
    lastStanding = parsed(text);
  }
  return lastStanding;
}

/** The saved device, or null when there is none, or none we can trust. */
export function savedDevice(): ThisDevice | null {
  return savedStanding().device;
}

/** Whether the server last said this device is blocked. */
export function savedBlocked(): boolean {
  return savedStanding().blocked;
}

// A copy we can't read, written by another version of the app or by hand, reads as nothing saved: the
// next check asks the server, which knows. Better that than a top bar naming a shop wrongly.
function parsed(text: string | null): Standing {
  if (text === null) return NOT_REGISTERED;
  try {
    const value: unknown = JSON.parse(text);
    return isStanding(value) ? value : NOT_REGISTERED;
  } catch {
    return NOT_REGISTERED;
  }
}

function isStanding(value: unknown): value is Standing {
  return (
    isMap(value) &&
    typeof value.blocked === "boolean" &&
    (value.device === null || isThisDevice(value.device))
  );
}

function isThisDevice(value: unknown): value is ThisDevice {
  if (!isMap(value)) return false;
  const { id, name, code, shop, homeSide } = value;
  return (
    typeof id === "string" &&
    typeof name === "string" &&
    typeof code === "number" &&
    isMap(shop) &&
    typeof shop.id === "string" &&
    typeof shop.name === "string" &&
    typeof shop.code === "string" &&
    isMap(homeSide) &&
    typeof homeSide.id === "string" &&
    typeof homeSide.code === "string" &&
    typeof homeSide.name === "string"
  );
}

// A plain JSON object: not nothing, and not a list, which typeof also calls "object".
function isMap(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

// Every screen showing the device, told when the saved copy changes.
const listeners = new Set<() => void>();

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  // "storage" comes when another tab of the app saves a copy: this tab follows it.
  window.addEventListener("storage", listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", listener);
  };
}

function save(standing: Standing): void {
  // Nothing to keep is kept as nothing: not registered, and not blocked.
  const text =
    standing.device === null && !standing.blocked
      ? null
      : JSON.stringify(standing);
  try {
    // Written only when it changed: the check runs every few minutes, and each write would wake every
    // other tab of the app with a "storage" event for nothing.
    if (text === window.localStorage.getItem(DEVICE_STORAGE_KEY)) return;
    if (text === null) window.localStorage.removeItem(DEVICE_STORAGE_KEY);
    else window.localStorage.setItem(DEVICE_STORAGE_KEY, text);
  } catch {
    // Storage refused (see savedStanding): nothing can be kept, and nothing breaks.
    return;
  }
  for (const listener of listeners) listener();
}

/** Keeps the device the server named, working, or forgets it (null): either way, no longer blocked, as
 * the server just answered without a block. Every screen is told. */
export function saveDevice(device: ThisDevice | null): void {
  save({ device, blocked: false });
}

/** Keeps the server's block, with the device it was known as, and tells every screen: the lock covers
 * them all (device-lock.tsx). */
export function saveBlocked(): void {
  save({ device: savedDevice(), blocked: true });
}

/**
 * This device, or null while it isn't registered. useSyncExternalStore is React's way to read something
 * kept outside React. The build has no browser, so pages are built knowing no device (the last
 * argument); in the browser, React then reads the saved copy at once.
 */
export function useThisDevice(): ThisDevice | null {
  return useSyncExternalStore(subscribe, savedDevice, () => null);
}

/** Whether this device is blocked. Built as not blocked, as the build knows no device. */
export function useDeviceBlocked(): boolean {
  return useSyncExternalStore(subscribe, savedBlocked, () => false);
}
