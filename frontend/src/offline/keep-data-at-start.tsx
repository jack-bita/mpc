// keep-data-at-start.tsx — asks the browser to keep the shop's data, and starts listening for the install
// offer, as every page opens (SYNC-12, 03 §6.7). The root layout renders it once; it shows nothing.
//
// At the start, not on the Kompyuta hii page: the data needs keeping whether or not anyone opens that page,
// and Chrome's install offer comes once, early, so a listener added later would miss it (keep-data.ts).
//
// "use client": it runs in the browser only, after the page is on screen.
"use client";

import { useEffect } from "react";

import { askToKeepData, watchInstall } from "./keep-data";

export function KeepDataAtStart(): null {
  useEffect(() => {
    void askToKeepData();
    return watchInstall();
  }, []);
  return null;
}
