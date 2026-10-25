// service-worker.tsx — starts the service worker from every page (SPIKE-1). layout.tsx renders it once.
//
// A client component: registering runs in the browser, after the page has loaded, never during the
// build. It shows nothing yet; the update prompt, Toleo jipya, comes next.
"use client";

import { useEffect } from "react";

import { registerServiceWorker } from "@/offline/service-worker";

export function ServiceWorker() {
  // After the page is on screen, so registering never slows the first paint. The empty list []: only
  // once, when the component first appears, not on every re-render.
  useEffect(() => {
    registerServiceWorker();
  }, []);

  return null;
}
