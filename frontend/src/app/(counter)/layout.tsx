// layout.tsx — the counter area: every screen a seller uses at the counter, under the shop's frame
// (UI-1, 03 §7.1).
//
// (counter) in brackets is a route group: Next.js gathers the screens in this folder under one layout,
// and leaves the folder's name out of their web address, so sale/page.tsx opens at /sale/.
//
// Counter screens (sale, payment, repayment, quick customer, drawer, clock-in) read the device's own
// database and never call the server, so they work the same with or without the internet. That is why
// this area has no Inahitaji mtandao banner: nothing here needs the network. The first screen comes
// with the sale cards; until then the area is ready and empty.
import type { ReactNode } from "react";

import { AppFrame } from "@/components/app-frame";

export default function CounterLayout({ children }: { children: ReactNode }) {
  return <AppFrame area="counter">{children}</AppFrame>;
}
