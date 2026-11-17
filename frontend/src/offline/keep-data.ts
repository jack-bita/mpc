// keep-data.ts — keeping the shop's data on this laptop for good (SYNC-12, 03 §6.7): asking the browser
// for persistent storage, and installing the app. It owns what the app knows of both, for the page that
// shows them (app/(counter)/this-laptop/).
//
// Why ask at all: by default a browser's storage is "best effort". When the disk runs short, the browser
// may wipe a site's data by itself, with no question, and the shop's database with it, unsent clock-ins
// included. A site the browser has agreed to keep ("persistent") is wiped only by a person, in the
// browser's own settings. Chrome and Edge answer by themselves, with no question on screen: yes for an
// installed app, or a site used often or bookmarked. So installing the app is also the way to a yes.
//
// Both answers live here, in this file's memory, read through useSyncExternalStore as this-device.ts
// does: the root layout asks as every page opens (keep-data-at-start.tsx), long before anyone opens the
// page, and the page reads what came back. SPIKE-1's report: on localhost Chrome says no even to the
// installed app, so development and the end-to-end tests always show "not kept"; only the demo or a real
// laptop proves the yes.
import { useSyncExternalStore } from "react";

/** The browser's answer. `asking` until it comes; `cannot_ask` for a browser with no such question
 * (an old one), or one that threw while asked. */
export type KeptState = "asking" | "kept" | "not_kept" | "cannot_ask";

/** Chrome's and Edge's event that offers the install (not in TypeScript's own list of the browser's
 * types, as other browsers have none). `prompt()` shows the browser's own install question. */
export interface InstallPromptEvent extends Event {
  prompt(): Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

/** How the app stands on this laptop: installed, offered (the browser has an install ready, so a button
 * can open it), or neither, where the page shows the menu's steps instead. */
export type InstallState =
  | { kind: "installed" }
  | { kind: "offered"; offer: InstallPromptEvent }
  | { kind: "steps" };

interface Known {
  kept: KeptState;
  install: InstallState;
}

// One object, replaced on each change, never edited: useSyncExternalStore compares it by identity, so a
// new object is what tells React to redraw.
let known: Known = { kept: "asking", install: { kind: "steps" } };
const listeners = new Set<() => void>();

function tell(next: Partial<Known>): void {
  known = { ...known, ...next };
  for (const listener of listeners) listener();
}

/**
 * Asks the browser to keep this site's data for good, and keeps its answer. Safe to call again: a site
 * already kept answers yes at once (persisted), and asking again a site refused costs nothing, while the
 * answer may change, as a laptop that installed the app since gets a yes.
 */
export async function askToKeepData(
  storage: StorageManager | undefined = globalThis.navigator?.storage,
): Promise<KeptState> {
  let kept: KeptState;
  if (storage?.persist === undefined || storage.persisted === undefined)
    kept = "cannot_ask";
  else {
    try {
      // Asked first, so a yes from before never asks again.
      kept =
        (await storage.persisted()) || (await storage.persist())
          ? "kept"
          : "not_kept";
    } catch (error) {
      // A browser that blocks storage altogether throws here: the page says this browser can't keep it.
      console.error("asking to keep the data failed", error);
      kept = "cannot_ask";
    }
  }
  tell({ kept });
  return kept;
}

/** True when this page runs as the installed app, in its own window, not in a browser's tab. */
function runsInstalled(): boolean {
  return globalThis.matchMedia?.("(display-mode: standalone)").matches ?? false;
}

/**
 * Starts listening for the browser's install offer and for the install itself. Called once, as the app
 * opens: Chrome fires its offer early, once, and an offer nobody was listening for is gone. Hands back
 * the function that stops listening.
 */
export function watchInstall(): () => void {
  if (runsInstalled()) tell({ install: { kind: "installed" } });

  function offered(event: Event) {
    // Keeps Chrome's own small install bar away: the page's button opens the same question, when the
    // manager chooses, not in the middle of a sale.
    event.preventDefault();
    tell({
      install: { kind: "offered", offer: event as InstallPromptEvent },
    });
  }
  function installed() {
    tell({ install: { kind: "installed" } });
  }
  window.addEventListener("beforeinstallprompt", offered);
  window.addEventListener("appinstalled", installed);
  return () => {
    window.removeEventListener("beforeinstallprompt", offered);
    window.removeEventListener("appinstalled", installed);
  };
}

/** Opens the browser's own install question, once: an offer can be used only once. Accepted, the
 * `appinstalled` event follows and the page says so; dismissed, the page shows the menu's steps. */
export async function install(offer: InstallPromptEvent): Promise<void> {
  await offer.prompt();
  const { outcome } = await offer.userChoice;
  if (outcome === "dismissed") tell({ install: { kind: "steps" } });
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Both answers, read live: the page redraws as each one arrives. */
export function useKeepData(): Known {
  return useSyncExternalStore(
    subscribe,
    () => known,
    // The build's HTML, made where no browser runs: nothing known yet.
    () => known,
  );
}

/** Tests only: forget every answer, as a new page does. */
export function forgetKeepData(): void {
  tell({ kept: "asking", install: { kind: "steps" } });
}
