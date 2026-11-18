// in-app-moves.tsx — remembers, for this tab, that the person has moved from one of the app's pages to
// another, so the page header's back arrow knows going back stays inside the app (page-header.tsx).
//
// Why not the browser's history alone: it can't say whose pages it holds. In Chrome, a bookmark opened from
// a new tab leaves the new-tab page in the history, so history.length is 2 and back() would take the
// person out of the app (the branch's review, 17 Nov 2026). This note is set only by the app's own moves:
//   - a move inside the app, as Next.js changes the address with no new page (the path changes), that
//     added a page to the tab's history (a link, a push), so the page before it is ours. Not a redirect
//     (router.replace), which changes the address in place: a bookmark to /office/ opened from Chrome's
//     new tab while logged out lands on /login/ with Chrome's page still before it (OPS-13's review);
//   - a whole page loaded from one of the app's own, as a login's redirect does (the referrer is ours).
// A bookmark, a typed address or a link from another site sets none of them, so the arrow then goes to
// the page's fallback instead.
//
// Kept in sessionStorage: one tab's memory, gone when the tab closes, as that tab's history is. A refresh
// keeps it, as it keeps the history. A browser that refuses storage (some private windows) never sets it:
// the arrow then always goes to the fallback, which is safe. It holds no person's data, so logging out
// leaves it. A browser keeps some 50 pages of a tab's history at most, so in a tab that long a push adds
// none: a move there may go unnoted, and the arrow uses the fallback, which is safe too.
//
// "use client": it reads the address and the tab's memory, which only the browser holds.
"use client";

import { usePathname } from "next/navigation";
import { useEffect, useRef } from "react";

/** The tab-memory key: "1" once the person has moved between the app's own pages in this tab. */
export const MOVED_IN_APP = "mpc.movedInApp";

/** Whether the person reached this page from another of the app's, in this tab. */
export function movedInApp(): boolean {
  try {
    return window.sessionStorage.getItem(MOVED_IN_APP) === "1";
  } catch {
    // Storage refused: as if never moved, so the arrow goes to the page's safe fallback.
    return false;
  }
}

function noteMove(): void {
  try {
    window.sessionStorage.setItem(MOVED_IN_APP, "1");
  } catch {
    // Storage refused: nothing to note; the arrow uses its fallback.
  }
}

/** Whether this page was loaded whole from one of the app's own pages. */
function loadedFromTheApp(): boolean {
  if (!document.referrer) return false;
  try {
    return new URL(document.referrer).origin === window.location.origin;
  } catch {
    return false;
  }
}

/** Notes the app's own moves; draws nothing. In the root layout, so every page counts. */
export function InAppMoves() {
  const path = usePathname();
  // The page this tab opened on, and how many pages its history held then: a move is another path after
  // it, with more pages than that, as a redirect adds none.
  const first = useRef<string | null>(null);
  const pagesAtFirst = useRef(0);
  useEffect(() => {
    if (first.current === null) {
      first.current = path;
      pagesAtFirst.current = window.history.length;
      if (loadedFromTheApp()) noteMove();
    } else if (
      path !== first.current &&
      window.history.length > pagesAtFirst.current
    ) {
      noteMove();
    }
  }, [path]);
  return null;
}
