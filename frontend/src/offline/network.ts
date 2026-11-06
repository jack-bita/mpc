// network.ts — whether this device has a network right now, for the screens that need one (UI-1,
// 03 §7.1).
//
// Office screens ask the server for everything, so they say Inahitaji mtandao when the network is gone.
// Counter screens never ask: they work the same either way, and don't use this.
//
// The browser's own answer, navigator.onLine, with its "online" and "offline" events. It is sure only
// one way: false means no network at all. True means the device is on a network, which may still not
// reach the internet (a Wi-Fi router whose mobile data is down). A request that fails then is the
// API client's to report (UI-2); this only covers the plain case, the network gone.
import { useSyncExternalStore } from "react";

function subscribe(listener: () => void): () => void {
  window.addEventListener("online", listener);
  window.addEventListener("offline", listener);
  return () => {
    window.removeEventListener("online", listener);
    window.removeEventListener("offline", listener);
  };
}

/**
 * True while the device has a network. useSyncExternalStore is React's way to read something kept
 * outside React. The build has no browser, so the page is built as online (the last argument); in the
 * browser, React then reads the real answer at once.
 */
export function useOnline(): boolean {
  return useSyncExternalStore(
    subscribe,
    () => navigator.onLine,
    () => true,
  );
}
