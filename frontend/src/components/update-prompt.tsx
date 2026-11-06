// update-prompt.tsx — starts the service worker from every page, and shows the Toleo jipya bar when a
// new version is ready (SPIKE-1, 03 §6.8). layout.tsx renders it once, on every page.
//
// A client component: registering runs in the browser, after the page has loaded, never during the
// build. When a version counts as ready is decided in src/offline/service-worker.ts; this file only
// shows the bar and passes the tap on.
"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "use-intl";

import { Button } from "@/components/design/button";
import { ON_GREEN } from "@/components/design/top-bar";
import { cn } from "@/lib/utils";
import {
  type ApplyUpdate,
  registerServiceWorker,
} from "@/offline/service-worker";

export function UpdatePrompt() {
  // The words come from the open book, Swahili or English (ADR-0040).
  const t = useTranslations("update");
  // null while there is no new version; the switch function once one is ready.
  const [apply, setApply] = useState<ApplyUpdate | null>(null);

  // After the page is on screen, so registering never slows the first paint. The empty list []: only
  // once, when the component first appears, not on every redraw.
  useEffect(() => {
    // setApply(() => next), not setApply(next): given a function, a React setter calls it to work out
    // the new value. Wrapping it in one more function stores the switch function itself.
    void registerServiceWorker((next) => setApply(() => next));
  }, []);

  return (
    // Always on the page, hidden from the eye (sr-only) until a new version is ready. Its words sit in a
    // role="status" box, which a screen reader says when its text changes, once it has finished what
    // it was saying. A box that appears with its text already in it may not be said at all (alert.tsx),
    // so the box is here from the start, empty, and the words arrive in it.
    // Once ready: fixed to the bottom of the screen, above the page, on the shop's green (ON_GREEN, which
    // also makes the focus ring white, as the blue one reads at only 1.74:1 on green).
    // print:hidden: a new version can be waiting while a slip prints, and this bar sits above every
    // page, so without it the customer's paper would carry it (SPIKE-2).
    <div
      className={cn(
        apply
          ? "fixed inset-x-0 bottom-0 flex items-center justify-between gap-4 p-4"
          : "sr-only",
        apply && ON_GREEN,
        "print:hidden",
      )}
    >
      <p role="status">{apply ? t("ready") : null}</p>
      {/* The bar kind, the only button that can sit on the green (button.tsx). Big: 52 px high, a
          finger's tap target on a phone (03 §7.3). */}
      {apply ? (
        <Button kind="bar" onClick={apply}>
          {t("apply")}
        </Button>
      ) : null}
    </div>
  );
}
