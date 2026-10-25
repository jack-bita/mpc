// service-worker.tsx — starts the service worker from every page, and shows the Toleo jipya bar when a
// new version is ready (SPIKE-1, 03 §6.8). layout.tsx renders it once, on every page.
//
// A client component: registering runs in the browser, after the page has loaded, never during the
// build. When a version counts as ready is decided in src/offline/service-worker.ts; this file only
// shows the bar and passes the tap on.
"use client";

import { useEffect, useState } from "react";

import {
  type ApplyUpdate,
  registerServiceWorker,
} from "@/offline/service-worker";

// Screen text comes from the message files (ADR-0032). UI-1 swaps this import for next-intl.
import sw from "../../messages/sw.json";

export function ServiceWorker() {
  // null while there is no new version; the switch function once one is ready.
  const [apply, setApply] = useState<ApplyUpdate | null>(null);

  // After the page is on screen, so registering never slows the first paint. The empty list []: only
  // once, when the component first appears, not on every redraw.
  useEffect(() => {
    // setApply(() => next), not setApply(next): given a function, a React setter calls it to work out
    // the new value. Wrapping it in one more function stores the switch function itself.
    void registerServiceWorker((next) => setApply(() => next));
  }, []);

  // No new version: show nothing.
  if (!apply) return null;

  return (
    // role="status": a screen reader reads the bar out when it appears, without pulling the person away
    // from what they are doing. Fixed to the bottom of the screen, above the page.
    <div
      role="status"
      className="fixed inset-x-0 bottom-0 flex items-center justify-between gap-4 bg-primary p-4 text-primary-foreground"
    >
      <span>{sw.update.ready}</span>
      {/* A big tap target for phones (03 §7.3): at least 48 pixels high. */}
      <button
        type="button"
        onClick={apply}
        className="min-h-12 rounded-md bg-background px-5 font-semibold text-foreground"
      >
        {sw.update.apply}
      </button>
    </div>
  );
}
