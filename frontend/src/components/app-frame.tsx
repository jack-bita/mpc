// app-frame.tsx — the frame around every counter and office screen: the green top bar, the side band
// under it, and the screen itself (UI-1, 03 §7.1). Both areas' layouts use it, (counter)/layout.tsx and
// (office)/layout.tsx, so the shop, the side and the bar's buttons are wired in one place.
//
// The bar names the device's shop and home side, "MPC · Dawa", once the device is registered (UI-3):
// a laptop shows where it belongs before anyone logs in at it. A phone that is only a manager's own
// knows no device, and its bar names nothing until the manager logs in (UI-5). No band yet: no side
// says which look it gets (04 §20, item 19). UI-4 adds who is logged in, and the side they work on.
//
// "use client": it reads the device's saved copy, which only the browser holds (this-device.ts).
"use client";

import type { ReactNode } from "react";

import { TopBar } from "@/components/design/top-bar";
import { LanguageButton } from "@/components/language-button";
import { useThisDevice } from "@/features/devices/this-device";

/** The two areas (03 §7.1): the counter works offline; the office needs the internet. */
export type Area = "counter" | "office";

export function AppFrame({
  area,
  notice,
  children,
}: {
  area: Area;
  /** A message under the bar, for the whole area, like the office's Inahitaji mtandao. */
  notice?: ReactNode;
  children: ReactNode;
}) {
  const device = useThisDevice();

  return (
    // data-area: which area a screen is in, for tests and for the eye in the browser's tools.
    // min-h-svh: the full height of the phone's visible screen, browser bars excluded.
    <div data-area={area} className="flex min-h-svh flex-col">
      <TopBar
        shop={device?.shop.name}
        side={device ? { name: device.homeSide.name } : undefined}
        actions={<LanguageButton />}
      />
      {notice}
      {/* The one <main> of the page: a screen inside an area doesn't write its own. */}
      <main className="flex-1 p-4">{children}</main>
    </div>
  );
}
