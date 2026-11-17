// layout.tsx — the setup area: the screens a device uses before it belongs to a shop, today only
// Sajili kifaa hiki (UI-3, 03 §7.2), under the shop's frame.
//
// (setup) in brackets is a route group: Next.js gathers the screens in this folder under one layout,
// and leaves the folder's name out of their web address, so register-device/page.tsx opens at
// /register-device/.
//
// Outside the counter area, as registering calls the server, which a counter screen never does (rule 5,
// ADR-0019). It needs the internet, so it says Inahitaji mtandao while the network is gone, as the
// office area does.
import type { ReactNode } from "react";

import { AppFrame } from "@/components/app-frame";
import { OfflineBanner } from "@/components/offline-banner";

export default function SetupLayout({ children }: { children: ReactNode }) {
  return (
    <AppFrame area="setup" notice={<OfflineBanner />}>
      {children}
    </AppFrame>
  );
}
