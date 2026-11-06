// app-frame.tsx — the frame around every counter and office screen: the green top bar, the side band
// under it, and the screen itself (UI-1, 03 §7.1). Both areas' layouts use it, (counter)/layout.tsx and
// (office)/layout.tsx, so the shop, the side and the bar's buttons are wired in one place.
//
// The shop and the side aren't known yet: UI-3 tells a device its shop and home side, and UI-4 who is
// logged in. Until then the bar shows only the language button.
import type { ReactNode } from "react";

import { TopBar } from "@/components/design/top-bar";
import { LanguageButton } from "@/components/language-button";

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
  return (
    // data-area: which area a screen is in, for tests and for the eye in the browser's tools.
    // min-h-svh: the full height of the phone's visible screen, browser bars excluded.
    <div data-area={area} className="flex min-h-svh flex-col">
      <TopBar actions={<LanguageButton />} />
      {notice}
      {/* The one <main> of the page: a screen inside an area doesn't write its own. */}
      <main className="flex-1 p-4">{children}</main>
    </div>
  );
}
