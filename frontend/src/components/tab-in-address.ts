// tab-in-address.ts — what a page shows, kept in its address: its open tab, /settings/?tab=money (SHOP-5),
// /flags/?tab=closed, and a list's filter, /flags/?side=…&kind=device_gap (CTRL-4). It owns the one way such a word is
// written, which Next.js's router makes easy to get wrong, so no page writes its own, and the address's name for the
// open tab (TAB_PARAM).
//
// "use client": it keeps state and reads the address, in the browser's React.
"use client";

import { useState } from "react";

/** The address's name for the open tab: /settings/?tab=money. */
export const TAB_PARAM = "tab";

/** The open tab, as the address names it, and a way to change both. */
export function useTabInAddress(): [string | null, (value: string) => void] {
  return useWordInAddress(TAB_PARAM);
}

/** One word of the address, by its name, and a way to change both; null takes it out. It replaces the address rather
 * than adding to the history: the back arrow and the browser's back leave the page, as a person expects, rather than
 * stepping through every tab they opened; and coming back to the page finds what they left.
 *
 * Read from the address on the first draw: the page's tabs come only once the server has answered, so always in
 * the browser, never in the page built ahead of time (ADR-0016), which has no address. The typeof check
 * keeps that true even if a later change draws them sooner. Read once: a link to the same page with another
 * word would not change it. No such link exists; one that comes must set the word itself. */
export function useWordInAddress(
  name: string,
): [string | null, (value: string | null) => void] {
  const [word, setWord] = useState<string | null>(() =>
    typeof window === "undefined"
      ? null
      : new URLSearchParams(window.location.search).get(name),
  );
  function choose(value: string | null) {
    setWord(value);
    const url = new URL(window.location.href);
    if (value === null) url.searchParams.delete(name);
    else url.searchParams.set(name, value);
    // null, never window.history.state: Next.js wraps replaceState, and given its own state (which carries
    // its __NA mark) it passes the call straight to the browser without noting the new address. Its router
    // would then still hold /settings/ with no tab, and put that back at its next update, dropping ?tab.
    // Given null, it copies its own state across and notes the address (Next's documented way).
    window.history.replaceState(null, "", url);
  }
  return [word, choose];
}
