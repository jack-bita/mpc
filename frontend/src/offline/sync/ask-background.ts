// ask-background.ts — the page's half of Background Sync: after each save, it asks the browser to wake
// the service worker once the network is there, so the record leaves even if the app is closed first
// (SYNC-16, 03 §6.5; the worker's half is background.ts).
//
// Chrome and Edge have it, on the shop phone and the laptops. Firefox and Safari don't: nothing is asked,
// and the open app's own moments send the record, as before (triggers.tsx). Nor is anything asked where
// the app has no service worker: `next dev`, or a browser that refused to install it.
//
// Asking is cheap. The browser keeps one sync by name, so asks made before it fires count once. With a
// network, it wakes the worker at once, so while the app is open and online the worker most often sends
// the record before the page's own 2 s: the page's push then finds nothing waiting. Either way the record
// goes once, as both take the same lock (lock.ts), and a refusal the worker hears reaches the page as a
// note (page-place.ts). Asked offline, the worker waits for the network, which is the point.
import { backgroundSyncTag } from "./background";

// Background Sync's part of a registration, which TypeScript's own types don't have yet.
interface WithSync {
  sync?: { register(tag: string): Promise<void> };
}

/** Whether this browser has Background Sync at all. */
export function hasBackgroundSync(): boolean {
  return "serviceWorker" in navigator && "SyncManager" in window;
}

/**
 * Asks the browser to wake the service worker for this shop once the network is there. Never throws: a
 * refused ask (the person switched off Background Sync in the browser's settings, say) leaves the record
 * to the open app's moments, which send it as before.
 */
export async function askForBackgroundSync(shopId: string): Promise<void> {
  if (!hasBackgroundSync()) return;
  try {
    // getRegistration, not `ready`: with no service worker installed, `ready` would wait forever.
    const registration = (await navigator.serviceWorker.getRegistration()) as
      (ServiceWorkerRegistration & WithSync) | undefined;
    await registration?.sync?.register(backgroundSyncTag(shopId));
  } catch {
    // Refused or failed: the open app still sends it (the 2 s after a save, the 30 s ticks).
  }
}
