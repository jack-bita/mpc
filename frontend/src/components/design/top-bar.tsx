// top-bar.tsx — the green bar at the top of every counter and office screen, with the side band under
// it (UI-1, ADR-0039). The godown's green, as the shop looks from the road.
//
// It writes where you are in words, "MPC · Dawa", so nobody has to tell the band's colours apart to
// know which side a screen is for (UI-8). On its right sit the bar's buttons (the language button,
// later Toka), all of the bar kind. It only sets the look: what the buttons do, and which shop and side
// to name, come from AppFrame (components/app-frame.tsx).
//
// "use client": it asks use-intl for its words, and use-intl's hooks run only in the browser's React.
// The area layouts that show it are server components (they run once, at build time), and without
// this line Next.js would build the bar as one too, and the build stops at the first page in an area
// ("createContext is not a function"). use-client.test.ts checks every file that uses use-intl.
"use client";

import type { ReactNode } from "react";
import { useTranslations } from "use-intl";

import { cn } from "@/lib/utils";

import { SideBand, type SideBandLook } from "./side-band";

/**
 * The green and its text, for anything that sits on green. It also sets --ring, the focus ring's
 * colour, to white for everything inside: our pieces read --ring, and the usual blue ring reads at
 * only 1.74:1 on the green, while white reads at 5.02:1 (UI-7). No piece has to change for it.
 */
export const ON_GREEN =
  "bg-primary text-primary-foreground [--ring:var(--primary-foreground)]";

/** A side, as the bar shows it: its name in words, and its band's look, when known. */
export interface BarSide {
  name: string;
  // Which side gets which look is still open (04 §20, item 19): no side says yet. Until one does, the
  // app gives no look, and the bar shows the side's name in words and no band (Jack, 7 Nov 2026), so
  // a look is never guessed. /design gives both looks by hand.
  band?: SideBandLook;
}

export function TopBar({
  shop,
  side,
  actions,
}: {
  /** The shop's name. Left out while the app knows none: on a device not yet registered, or a phone
   * that is only a manager's own (UI-3). */
  shop?: string;
  /** The side this screen is for: the device's home side for now (UI-3), the person's once someone
   * logs in (UI-4). Left out while the app knows none. */
  side?: BarSide;
  /** The bar's buttons, at its right end. */
  actions?: ReactNode;
}) {
  const t = useTranslations("topBar");

  // "MPC · Dawa", or only the shop's name while no side is known. The names are the shop's own, so
  // they read the same in both languages.
  const place =
    shop && side ? t("place", { shop, side: side.name }) : (shop ?? null);

  return (
    // <header> at the top of the page: a screen reader lists it as the page's banner, a landmark it
    // can jump to.
    <header>
      <div
        className={cn(
          // 64 px tall at least, so a big finger target fits with room to spare.
          "flex min-h-16 items-center justify-between gap-4 px-4 py-2",
          ON_GREEN,
        )}
      >
        {/* text-lg, semibold: read at a glance from where a seller stands. While no shop is known, an
            empty <div> keeps the buttons at the right end, with no empty paragraph for a screen
            reader to land on. */}
        {place ? <p className="text-lg font-semibold">{place}</p> : <div />}
        <div className="flex items-center gap-2">{actions}</div>
      </div>
      {side?.band ? <SideBand look={side.band} /> : null}
    </header>
  );
}
