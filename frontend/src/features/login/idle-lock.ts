// idle-lock.ts — a shared laptop locks itself when nobody has touched it for the shop's idle minutes
// (UI-4, 03 §5.9): a seller who walks away from the counter must not leave it open in her name.
//
// The server ends a PIN's session after the same minutes with no use of its own (AUTH-4), but selling at
// the counter uses the device's key, not the session, so the server's clock alone would never lock the
// screen. So the screen keeps a lock of its own, as long as `me` says (idle_minutes, read from the session
// itself, so the two end together).
//
// A watch, not an egg timer: it writes down when the laptop was last touched, and looks at the clock every
// few seconds, and as the laptop wakes or the tab comes back. A timer counting down would sleep with a
// closed lid, and wait out its last minutes after the lid opens, with the person still on the screen.
//
// Honest limit: a tap or a key press counts as use; reading a long screen without touching it doesn't.
import { useEffect, useEffectEvent } from "react";

/** How often the lock looks at the clock: it locks at most this late. */
export const IDLE_CHECK_EVERY = 10 * 1000;

/**
 * Calls `onIdle` once nobody has tapped or pressed a key for `minutes`. No minutes, no lock: a password on
 * a person's own phone, which isn't shared, has none (`me`, AUTH-4). Once more only after the next use.
 */
export function useIdleLock(
  minutes: number | null | undefined,
  onIdle: () => void,
): void {
  // The screen's latest onIdle, whatever it drew last: the watch below starts once for the session, and a
  // redraw must not start the minutes again.
  const idle = useEffectEvent(onIdle);

  useEffect(() => {
    if (!minutes) return;
    const limit = minutes * 60 * 1000;
    let lastUsed = Date.now();
    // Locked already, until the next use: the logout it starts takes a moment, and the checks meanwhile
    // must not send a second one.
    let locked = false;

    const used = () => {
      lastUsed = Date.now();
      locked = false;
    };
    const check = () => {
      if (!locked && Date.now() - lastUsed >= limit) {
        locked = true;
        idle();
      }
    };

    const every = window.setInterval(check, IDLE_CHECK_EVERY);
    window.addEventListener("pointerdown", used);
    window.addEventListener("keydown", used);
    // The laptop woke, or the tab came back to the front: look at once, not at the next check.
    document.addEventListener("visibilitychange", check);
    // Everything stops when the screen goes, or when the minutes change (a new person logs in).
    return () => {
      window.clearInterval(every);
      window.removeEventListener("pointerdown", used);
      window.removeEventListener("keydown", used);
      document.removeEventListener("visibilitychange", check);
    };
  }, [minutes]);
}
