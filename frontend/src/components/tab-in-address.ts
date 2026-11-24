// tab-in-address.ts — a page's open tab, kept in its address: /settings/?tab=money (SHOP-5), /flags/?tab=closed
// (CTRL-4). It owns the address's name for it (TAB_PARAM) and the one way it is written, which Next.js's router
// makes easy to get wrong, so no page writes its own.
//
// "use client": it keeps state and reads the address, in the browser's React.
"use client";

import { useState } from "react";

/** The address's name for the open tab: /settings/?tab=money. */
export const TAB_PARAM = "tab";

/** The open tab, as the address names it, and a way to change both. It replaces the address rather than
 * adding to the history: the back arrow and the browser's back leave the page, as a person expects, rather
 * than stepping through every tab they opened; and coming back to the page finds the tab they left.
 *
 * Read from the address on the first draw: the page's tabs come only once the server has answered, so always in
 * the browser, never in the page built ahead of time (ADR-0016), which has no address. The typeof check
 * keeps that true even if a later change draws the tabs sooner. Read once: a link to the same page with another
 * tab would not change it. No such link exists; one that comes must set the tab itself. */
export function useTabInAddress(): [string | null, (value: string) => void] {
  const [asked, setAsked] = useState<string | null>(() =>
    typeof window === "undefined"
      ? null
      : new URLSearchParams(window.location.search).get(TAB_PARAM),
  );
  function choose(value: string) {
    setAsked(value);
    const url = new URL(window.location.href);
    url.searchParams.set(TAB_PARAM, value);
    // null, never window.history.state: Next.js wraps replaceState, and given its own state (which carries
    // its __NA mark) it passes the call straight to the browser without noting the new address. Its router
    // would then still hold /settings/ with no tab, and put that back at its next update, dropping ?tab.
    // Given null, it copies its own state across and notes the address (Next's documented way).
    window.history.replaceState(null, "", url);
  }
  return [asked, choose];
}
