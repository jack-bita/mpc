// this-device.ts — which device this is, as the server last said: its name, its number, its shop and
// its home side (UI-3, 03 §5.9, step 3).
//
// Kept on the device (localStorage), so the top bar still names the shop with no network, and after a
// reload. The server is the one that knows: device-check.tsx asks it and saves the answer here. This
// file never calls the server itself, so any screen may read it, counter screens included: they will
// need the device's number for receipt numbers (D7), and they never import the API client (rule 5,
// ADR-0019).
//
// Nothing saved reads as "not registered": a new device, a phone that is only a manager's own, or a
// device whose saved copy was wiped. The next check puts it right if the server knows otherwise.
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

// The browser's key for the saved copy. "mpc." keeps it apart from anything else on the same address,
// as the language choice's "mpc.language" does.
export const DEVICE_STORAGE_KEY = "mpc.device";

// The last text read from storage, and what it meant. React asks for the saved copy on every draw, and
// wants the very same object back while nothing changed, or it draws again without end; reading JSON
// makes a new object each time. So it is read again only when the text itself changed.
let lastText: string | null = null;
let lastDevice: ThisDevice | null = null;

/** The saved copy, or null when there is none, or none we can trust. */
export function savedDevice(): ThisDevice | null {
  let text: string | null;
  try {
    text = window.localStorage.getItem(DEVICE_STORAGE_KEY);
  } catch {
    // A browser set to block every site's storage refuses even to read it. The device then knows
    // itself only until the page closes: such a browser can't run the counter anyway (language.ts).
    return null;
  }
  if (text !== lastText) {
    lastText = text;
    lastDevice = parsed(text);
  }
  return lastDevice;
}

// A copy we can't read as a device, written by another version of the app or by hand, reads as none:
// the next check asks the server, which knows. Better that than a top bar naming a shop wrongly.
function parsed(text: string | null): ThisDevice | null {
  if (text === null) return null;
  try {
    const value: unknown = JSON.parse(text);
    return isThisDevice(value) ? value : null;
  } catch {
    return null;
  }
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

/** Keeps what the server said about this device, or forgets it (null), and tells every screen. */
export function saveDevice(device: ThisDevice | null): void {
  const text = device === null ? null : JSON.stringify(device);
  try {
    // Written only when it changed: the check runs every few minutes, and each write would wake every
    // other tab of the app with a "storage" event for nothing.
    if (text === window.localStorage.getItem(DEVICE_STORAGE_KEY)) return;
    if (text === null) window.localStorage.removeItem(DEVICE_STORAGE_KEY);
    else window.localStorage.setItem(DEVICE_STORAGE_KEY, text);
  } catch {
    // Storage refused (see savedDevice): nothing can be kept, and nothing breaks.
    return;
  }
  for (const listener of listeners) listener();
}

/**
 * This device, or null while it isn't registered. useSyncExternalStore is React's way to read something
 * kept outside React. The build has no browser, so pages are built knowing no device (the last
 * argument); in the browser, React then reads the saved copy at once.
 */
export function useThisDevice(): ThisDevice | null {
  return useSyncExternalStore(subscribe, savedDevice, () => null);
}
