// offline-banner.tsx — the Inahitaji mtandao message on office screens, while the network is gone
// (UI-1, 03 §7.1). The office layout puts it under the top bar, (office)/layout.tsx.
//
// Built on the alert piece's info kind (UI-8): role="status", which a screen reader says when its text
// changes, once it has finished what it was saying. A box that appears with its text already in it
// may not be said at all (NVDA with Chrome, VoiceOver). So the box is always on the page: while online
// it is empty and hidden from the eye (sr-only), and when the network drops its words arrive in it.
"use client";

import { WifiOff } from "lucide-react";
import { useTranslations } from "use-intl";

import { Alert, AlertDescription, AlertTitle } from "@/components/design/alert";
import { useOnline } from "@/offline/network";

export function OfflineBanner() {
  const t = useTranslations("offline");
  const online = useOnline();

  return (
    // sr-only, not hidden: a hidden box is gone for a screen reader too, and a box that comes back
    // with its words in it may not be said. On a wrapper, not on the box: sr-only sets the position,
    // padding and border that the box's own look sets too, and only CSS order would decide between
    // them. m-4: the banner's own room under the top bar.
    <div className={online ? "sr-only" : "m-4"}>
      <Alert kind="info">
        {online ? null : (
          <>
            {/* The icon says the same as the title, so a screen reader skips it. */}
            <WifiOff aria-hidden="true" />
            <AlertTitle>{t("title")}</AlertTitle>
            <AlertDescription>{t("description")}</AlertDescription>
          </>
        )}
      </Alert>
    </div>
  );
}
