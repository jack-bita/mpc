// update-prompt.tsx — starts the service worker from every page, and shows the Toleo jipya bar when a
// new version is ready and no counter screen is busy (SPIKE-1, SYNC-13, 03 §6.8). layout.tsx renders it
// once, on every page.
//
// A tap sends the records still waiting first, then switches (03 §6.8: send the outbox, then update). An
// app a sync found too old for the server takes the same steps by itself, with no tap (sync/too-old.ts),
// and so does a tab the new version has taken over, the tab that tapped included: it reloads once the
// counter is quiet (service-worker.ts).
//
// A client component: registering runs in the browser, after the page has loaded, never during the
// build. When a version counts as ready is decided in src/offline/service-worker.ts, when the counter is
// busy in src/offline/busy.ts, and how the records go first in src/offline/sync/before-update.ts; this
// file only shows the bar and passes the tap on.
"use client";

import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { useTranslations } from "use-intl";

import { Button } from "@/components/design/button";
import { ON_GREEN } from "@/components/design/top-bar";
import { cn } from "@/lib/utils";
import {
  counterIsQuiet,
  QUIET_CHECK_EVERY,
  useCounterQuiet,
} from "@/offline/busy";
import {
  type ApplyUpdate,
  registerServiceWorker,
} from "@/offline/service-worker";
import { sendBeforeUpdate } from "@/offline/sync/before-update";
import { listenForTooOld, timesTold } from "@/offline/sync/too-old";

export function UpdatePrompt() {
  // The words come from the open book, Swahili or English (ADR-0040).
  const t = useTranslations("update");
  // null while there is no new version; the switch function once one is ready.
  const [apply, setApply] = useState<ApplyUpdate | null>(null);
  // True from the tap until the switch: the records go first, which may take a few seconds.
  const [sending, setSending] = useState(false);
  // Another tab switched, and this one still runs the old code (service-worker.ts): it reloads by itself.
  const [takenOver, setTakenOver] = useState(false);

  // After the page is on screen, so registering never slows the first paint. The empty list []: only
  // once, when the component first appears, not on every redraw. The regular looks for a new version run
  // until the bar leaves the page, which on the root layout is when the tab closes.
  useEffect(() => {
    // setApply(() => next), not setApply(next): given a function, a React setter calls it to work out
    // the new value. Wrapping it in one more function stores the switch function itself.
    const stopping = registerServiceWorker((next, kind) => {
      setApply(() => next);
      if (kind === "taken_over") setTakenOver(true);
    });
    return () => {
      void stopping.then((stop) => stop());
    };
  }, []);

  // Hidden while any counter screen, in any tab, is busy: a switch reloads the page, and a reload in the
  // middle of a sale loses it (Jack, 13 Nov 2026: the bar waits until the sale is finished, then shows).
  // Watched only while a version waits, so a laptop with nothing to update asks nothing.
  const quiet = useCounterQuiet(apply !== null);
  const shown = apply !== null && quiet;

  // One tap at a time, from the press to the switch. A ref, not the `sending` state: the state changes
  // only at the next redraw, after the tap's first wait, so a second press before it, a fast double tap
  // or a press during the bar's own try below, would read it unchanged and send and switch twice.
  const tapping = useRef(false);
  // The version switched to, by a tap or by the bar itself, once: a reload that doesn't come leaves the
  // bar for a tap, rather than telling the worker again at every redraw. A try that a new sale stopped is
  // forgotten, so the next quiet moment tries again.
  const triedAlone = useRef<ApplyUpdate | null>(null);

  // Looked at once more as the tap lands: another tab's sale may have started since the bar's last look
  // (busy.ts looks every 2 s). Busy now, the tap does nothing, and the bar hides at its next look.
  // Then the records still waiting go first; at most a few seconds, and the switch goes ahead whatever
  // the send's end (before-update.ts says why nothing is lost). Says whether it switched.
  const tap = async (): Promise<boolean> => {
    if (apply === null || tapping.current) return false;
    tapping.current = true;
    try {
      if (!(await counterIsQuiet())) return false;
      setSending(true);
      await sendBeforeUpdate();
      // Looked at again after the send: a sale may have started in the seconds it took. The bar then
      // hides until it is finished, and the next tap sends again, nothing by then, and switches.
      const switching = await counterIsQuiet();
      if (switching) {
        // Switched to, by this tap or by the bar itself: the bar's own try below leaves this version alone.
        triedAlone.current = apply;
        apply();
      }
      return switching;
    } catch (error) {
      // Nothing above should fail: the send and the looks each keep their own failures (before-update.ts,
      // busy.ts). One that did is a bug: the console says so, as for a sync's (triggers.tsx), and the bar
      // is ready again below, rather than the failure escaping unseen.
      console.error("update failed", error);
      return false;
    } finally {
      // Ready for another tap, however the tap ended: the switch reloads the page in a moment, and if it
      // doesn't, or anything above failed, a bar left disabled on "Inatuma…" would keep the laptop on the
      // old version with no way on, and the bar's own try below waits while it is.
      setSending(false);
      tapping.current = false;
    }
  };

  // Too old for the server (sync/too-old.ts): the pulls have stopped, and no change from the office
  // arrives, a suspension included, until the app updates. So it switches by itself, with no tap (Jack,
  // 13 Nov 2026), as soon as a version is ready and the counter is quiet: the same steps as a tap, the
  // records first. The service worker looks for the version at once (service-worker.ts). A tab another
  // tab switched does the same: its old code would fail at the first file the new version deleted.
  // Read as a count, so each sync that finds it redraws the bar, and the try below runs again (too-old.ts).
  const told = useSyncExternalStore(
    listenForTooOld,
    timesTold,
    // The build has no browser and no sync: never told.
    () => 0,
  );
  const tooOld = told > 0;
  // A try refused by a busy counter comes again at the bar's next look. The sale that refused it may be
  // over before then, and the bar's look then finds it quiet, as it was: nothing the bar reads changes, so
  // nothing would redraw it. This redraws it, once per refused try; a sale still open at that look hides
  // the bar, and the try waits for it to show again.
  const [, redrawToTryAgain] = useState(0);
  const tryAgainLater = useRef<ReturnType<typeof setTimeout> | undefined>(
    undefined,
  );
  useEffect(() => () => clearTimeout(tryAgainLater.current), []);
  // No list of what it reads: it looks again after every redraw, and does nothing until all of it holds.
  // Each sync that finds the app too old redraws the bar too.
  useEffect(() => {
    if (!(tooOld || takenOver) || !shown || sending) return;
    // Switched to already, by the bar or a tap. A try that met a tap on its way was refused as a second tap
    // and forgotten; once that tap switches, this version is marked, so the try never sends again.
    if (triedAlone.current === apply) return;
    triedAlone.current = apply;
    void tap().then((switched) => {
      if (switched) return;
      triedAlone.current = null;
      clearTimeout(tryAgainLater.current);
      tryAgainLater.current = setTimeout(
        () => redrawToTryAgain((times) => times + 1),
        QUIET_CHECK_EVERY,
      );
    });
  });

  return (
    // Always on the page, hidden from the eye (sr-only) until a new version is ready and the counter is
    // quiet. Its words sit in a role="status" box, which a screen reader says when its text changes, once
    // it has finished what it was saying. A box that appears with its text already in it may not be said
    // at all (alert.tsx), so the box is here from the start, empty, and the words arrive in it.
    // Once ready: fixed to the bottom of the screen, above the page, on the shop's green (ON_GREEN, which
    // also makes the focus ring white, as the blue one reads at only 1.74:1 on green).
    // print:hidden: a new version can be waiting while a slip prints, and this bar sits above every
    // page, so without it the customer's paper would carry it (SPIKE-2).
    <div
      className={cn(
        shown
          ? "fixed inset-x-0 bottom-0 flex items-center justify-between gap-4 p-4"
          : "sr-only",
        shown && ON_GREEN,
        "print:hidden",
      )}
    >
      <p role="status">
        {shown ? (sending ? t("sending") : t("ready")) : null}
      </p>
      {/* The bar kind, the only button that can sit on the green (button.tsx). Big: 52 px high, a
          finger's tap target on a phone (03 §7.3). Disabled while the records go, so a second tap
          doesn't send them again beside the first. */}
      {shown ? (
        <Button kind="bar" disabled={sending} onClick={() => void tap()}>
          {t("apply")}
        </Button>
      ) : null}
    </div>
  );
}
