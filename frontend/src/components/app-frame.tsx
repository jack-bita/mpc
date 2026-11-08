// app-frame.tsx — the frame around every counter, office and setup screen: the green top bar, the side
// band under it, and the screen itself (UI-1, 03 §7.1). Each area's layout uses it, (counter)/layout.tsx,
// (office)/layout.tsx and (setup)/layout.tsx, so the shop, the side and the bar's buttons are wired in
// one place. The home page's PIN login uses it too, on a registered device (UI-4).
//
// The bar names the device's shop and home side, "MPC · Dawa", once the device is registered (UI-3):
// a laptop shows where it belongs before anyone logs in at it. A phone that is only a manager's own
// knows no device, and its bar names nothing until the manager logs in: then the office's frame hands in
// the shop of whoever is logged in (office-frame.tsx, UI-5). No band yet: no side
// says which look it gets (04 §20, item 19). Once someone logs in at the device, the bar names them, and
// the side they work on in place of the device's (UI-4): a screen that knows who is here hands both in.
// The language button goes then: it is the laptop's own language, and the person reads theirs (UI-9).
//
// "use client": it reads the device's saved copy, which only the browser holds (this-device.ts).
"use client";

import type { ReactNode } from "react";

import { type BarSide, TopBar } from "@/components/design/top-bar";
import { LanguageButton } from "@/components/language-button";
import { useThisDevice } from "@/features/devices/this-device";

/** The areas (03 §7.1, §7.2): the counter works offline; the office needs the internet; setup is where a
 * device registers, before it belongs to a shop, and needs the internet too (UI-3); login is the home
 * page's PIN login on a registered device (UI-4), and the owner's and managers' password pages
 * (app/(login)/, UI-5), which call the server, so they are outside the counter lock too. */
export type Area = "counter" | "office" | "setup" | "login";

export function AppFrame({
  area,
  notice,
  shop,
  person,
  side,
  actions,
  children,
}: {
  area: Area;
  /** A message under the bar, for the whole area, like the office's Inahitaji mtandao. */
  notice?: ReactNode;
  /** The shop of whoever is logged in, by its name: "MPC". Left out, the device's shop, as before anyone
   * logs in; a phone that is only a manager's own knows no device, so only a login names its shop (UI-5). */
  shop?: string;
  /** Who is logged in at this device, by the name the shop calls them: "Asha". Left out while nobody
   * is (UI-4). */
  person?: string;
  /** The side the person works on (sideAt, who-is-here.ts). Left out, the device's home side, as before
   * anyone logs in. */
  side?: BarSide;
  /** A screen's own buttons for the bar, before the language button: Badilisha mtu and Toka (UI-4). */
  actions?: ReactNode;
  children: ReactNode;
}) {
  const device = useThisDevice();
  const homeSide = device ? { name: device.homeSide.name } : undefined;

  return (
    // data-area: which area a screen is in, for tests and for the eye in the browser's tools.
    // min-h-svh: the full height of the phone's visible screen, browser bars excluded.
    <div data-area={area} className="flex min-h-svh flex-col">
      <TopBar
        shop={shop ?? device?.shop.name}
        side={side ?? homeSide}
        actions={
          <>
            {/* Who is here, read at a glance from where the next person stands. */}
            {person ? <p className="text-lg font-semibold">{person}</p> : null}
            {actions}
            {/* The laptop's own language, for the tiles and the login pages: only while nobody is logged
                in. Someone who is reads their own, and changes it in Mipangilio yangu, the one place for
                it (Jack, UI-9). */}
            {person ? null : <LanguageButton />}
          </>
        }
      />
      {notice}
      {/* The one <main> of the page: a screen inside an area doesn't write its own. */}
      <main className="flex-1 p-4">{children}</main>
    </div>
  );
}
