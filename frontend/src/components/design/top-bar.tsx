// top-bar.tsx — the green bar at the top of every counter and office screen, with the side band under
// it (UI-1, ADR-0039). The godown's green, as the shop looks from the road.
//
// It writes where you are in words, "MPC · Dawa", so nobody has to tell the band's colours apart to
// know which side a screen is for (UI-8). On its right sit the bar's buttons (the language button,
// later Toka), all of the bar kind. It only sets the look: what the buttons do, and which shop and side
// to name, come from AppFrame (components/app-frame.tsx).
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

/** A side, as the bar shows it: its name in words, and its band's look. */
export interface BarSide {
  name: string;
  // Which side gets which look is still open (04 §20, item 19), so it is always given, never guessed.
  band: SideBandLook;
}

export function TopBar({
  shop,
  side,
  actions,
}: {
  /** The shop's name. Left out until the app knows it (UI-3). */
  shop?: string;
  /** The side this screen is for. Left out until the app knows it (UI-3, UI-4). */
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
        {/* text-lg, semibold: read at a glance from where a seller stands. */}
        <p className="text-lg font-semibold">{place}</p>
        <div className="flex items-center gap-2">{actions}</div>
      </div>
      {side ? <SideBand look={side.band} /> : null}
    </header>
  );
}
