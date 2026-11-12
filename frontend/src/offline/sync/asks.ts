// asks.ts — how the counter asks for a sync without calling the server: "a record was saved" and
// "Tuma sasa" (SYNC-9, 03 §6.5).
//
// A counter screen never calls the server (rule 5, ADR-0019), so it can't start a sync itself: the sync
// sends requests. It says what happened here instead, and the sync's moments (triggers.tsx), which may
// call the server, listen and act on it. This file imports nothing, so any counter screen may use it
// without bringing the API client with it.
//
// Asks are heard in this tab only. A tab works for one shop, its device's (this-device.ts), so an ask
// names no shop: the moments of this tab sync that one. Another tab's saves are its own moments' to send.

/** What the counter asks: a record was saved (the sync goes 2 s later), or someone pressed Tuma sasa
 * (it goes now, even during a wait). */
export type SyncAskKind = "saved" | "send_now";

type Listener = (kind: SyncAskKind) => void;

const listeners = new Set<Listener>();

// Each listener is told on its own, and one that fails is only logged. The save that asks is done by the
// time it tells (outbox.ts): a listener's failure thrown back to it would make a saved record look
// failed, and a seller who saw "not saved" would tap again, making a second record with a new id, a
// clock-in twice. A failed listener misses one moment at most; the next 30 s tick still sends.
function tell(kind: SyncAskKind): void {
  for (const listener of listeners) {
    try {
      listener(kind);
    } catch (error) {
      console.error("a sync ask failed", error);
    }
  }
}

/** A record was saved on this laptop: saveDocument (outbox.ts) says so once its transaction is in. */
export function tellRecordSaved(): void {
  tell("saved");
}

/** Someone pressed Tuma sasa: the sync goes now, the push even during a wait. The button is on the first
 * counter screen (SYNC-11). */
export function askToSendNow(): void {
  tell("send_now");
}

/** Listens for the counter's asks; the returned function stops listening. */
export function listenForAsks(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
