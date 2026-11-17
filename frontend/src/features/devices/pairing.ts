// pairing.ts — a new device asks to join a shop: it gets a code to show, and counts down until the code
// expires (UI-3, 03 §5.9, step 1).
//
// POST /api/devices/v1/pairing/ answers with the code and when it expires (10 minutes on, by the
// server's clock), and puts the device's key in a cookie, which page scripts can never read (AUTH-2).
// The manager types the code on their own phone; the device then learns it is registered from its own
// check (device-check.tsx).
//
// The countdown trusts the server's clock, not the device's. Many shop laptops keep a wrong time (a flat
// clock battery, a wrong time zone): a laptop an hour behind would count an hour too long, and one an
// hour ahead would call every new code expired at once, and stop waiting for the manager. So the code's
// life is measured on the server's clock, from its answer's Date header to the expiry, and counted down
// on the device's clock from the moment the answer arrived: only the device's clock's pace matters, never
// its time.
import { api, csrfHeader } from "@/api/client";
import { answerOf } from "@/api/refusal";

import { checkThisDevice } from "./device-check";

/** A code to show, and when it expires, as a time on this device's own clock. */
export interface Pairing {
  /** As the server wrote it: 8 letters and digits, with no look-alikes (no 0 and O, no 1 and I). */
  code: string;
  /** Milliseconds, on this device's clock (Date.now()), when the code stops working. */
  deadline: number;
}

/**
 * The code's life, in milliseconds: from the server's time at its answer (the Date header) to the
 * expiry it sent. With no Date header, or one we can't read, the device's own time at the answer stands
 * in, which is only as right as its clock. Never below zero.
 */
export function lifetime(
  expiresAt: string,
  serverDate: string | null,
  receivedAt: number,
): number {
  const serverNow = serverDate === null ? NaN : Date.parse(serverDate);
  // A Date header holds whole seconds, cut down: the server's real time was up to a second later. It is
  // counted as that second later, so the countdown ends up to a second early, less the time the answer
  // took to arrive: it ends after the code only on an answer slower than a second, and then by a
  // moment, which the manager's own confirm, refused as expired, says plainly.
  const from = Number.isNaN(serverNow) ? receivedAt : serverNow + 1000;
  return Math.max(0, Date.parse(expiresAt) - from);
}

/** Asks the server for a code. A refusal (too many tries, already registered) or no answer is thrown,
 * for the screen to show. */
export async function startPairing(): Promise<Pairing> {
  // The start is a change, so it needs the CSRF token (03 §5.9). The device's check gives the browser
  // its cookie as the app opens (DeviceMeView); a tap faster than that answer, on a slow network, asks
  // for it first. A failed check doesn't stop the start: its own answer says what went wrong.
  if (Object.keys(csrfHeader()).length === 0)
    await checkThisDevice().catch(() => null);

  const call = await api.POST("/api/devices/v1/pairing/");
  const receivedAt = Date.now();
  const started = await answerOf(Promise.resolve(call));
  return {
    code: started.code,
    deadline:
      receivedAt +
      lifetime(
        started.expires_at,
        call.response.headers.get("Date"),
        receivedAt,
      ),
  };
}

/** The code split in two groups of four, "K7QM-4RXT", the easier to read out loud. The server takes
 * it back with or without the dash (clean_typed_code). A code of another length stays as it is. */
export function codeForReading(code: string): string {
  return code.length === 8 ? `${code.slice(0, 4)}-${code.slice(4)}` : code;
}

/** Time left as minutes and seconds, "9:41", counting whole seconds up, so a new code reads "10:00"
 * and "0:00" only once it has expired. The same in both languages. */
export function timeLeft(deadline: number, now: number): string {
  const seconds = Math.max(0, Math.ceil((deadline - now) / 1000));
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${String(seconds % 60).padStart(2, "0")}`;
}
