// layout.tsx — the password pages of the owner and managers: Ingia, Umesahau nenosiri?, and later the new
// password from the email link (UI-5, 03 §5.9).
//
// (login) in brackets is a route group: its folder's name stays out of the web address, so
// login/page.tsx opens at /login/. These pages sit in AppFrame's login area, beside the home page's PIN
// login (UI-4): they call the server, so they are outside the counter's lock (rule 5), and need the
// internet, which the offline banner says while it is gone.
import type { ReactNode } from "react";

import { AppFrame } from "@/components/app-frame";
import { OfflineBanner } from "@/components/offline-banner";

export default function LoginLayout({ children }: { children: ReactNode }) {
  return (
    <AppFrame area="login" notice={<OfflineBanner />}>
      {children}
    </AppFrame>
  );
}
