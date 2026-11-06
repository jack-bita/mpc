// layout.tsx — the office area: every screen a manager or the owner uses to run the shop, under the
// shop's frame (UI-1, 03 §7.1).
//
// (office) in brackets is a route group: Next.js gathers the screens in this folder under one layout,
// and leaves the folder's name out of their web address, so products/page.tsx opens at /products/.
//
// Office screens (products, prices, deliveries, counts, cash-up, reports, staff, settings, devices,
// flags) ask the server for everything, so they need the internet: while the network is gone, every
// one of them says Inahitaji mtandao under the top bar. The first screen comes with PPL-4; until then
// the area is ready and empty.
import type { ReactNode } from "react";

import { AppFrame } from "@/components/app-frame";
import { OfflineBanner } from "@/components/offline-banner";

export default function OfficeLayout({ children }: { children: ReactNode }) {
  return (
    <AppFrame area="office" notice={<OfflineBanner />}>
      {children}
    </AppFrame>
  );
}
