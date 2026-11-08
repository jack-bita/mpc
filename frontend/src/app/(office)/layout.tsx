// layout.tsx — the office area: every screen a manager or the owner uses to run the shop, under the
// shop's frame (UI-1, 03 §7.1).
//
// (office) in brackets is a route group: Next.js gathers the screens in this folder under one layout,
// and leaves the folder's name out of their web address, so products/page.tsx opens at /products/.
//
// Office screens (products, prices, deliveries, counts, cash-up, reports, staff, settings, devices,
// flags) ask the server for everything, so they need the internet: while the network is gone, every
// one of them says Inahitaji mtandao under the top bar. They need a login too: the frame names who is
// logged in, and sends anyone who isn't to the way in (features/office/office-frame.tsx, UI-5). The
// office's home page, /office/, opens each screen the person may use.
import type { ReactNode } from "react";

import { OfficeFrame } from "@/features/office/office-frame";

export default function OfficeLayout({ children }: { children: ReactNode }) {
  return <OfficeFrame>{children}</OfficeFrame>;
}
