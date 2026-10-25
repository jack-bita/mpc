// page.tsx — the home page at "/": for now, the Karibu welcome and the app's version.
//
// "use client": every page in this app is a client component (ADR-0016), because pages
// will read the device's own data (Dexie) and must work with no server. Next.js still
// renders the page once at build time, so out/index.html already holds the first HTML.
"use client";

import { APP_VERSION } from "@/lib/version";

// The text lives in the message files, not here (ADR-0032). UI-1 swaps this direct import
// for next-intl's useTranslations().
import sw from "../../messages/sw.json";

export default function HomePage() {
  return (
    // min-h-svh: the full height of the phone's visible screen, browser bars excluded.
    <main className="flex min-h-svh flex-col items-center justify-center gap-2 p-4">
      <h1 className="text-4xl font-semibold tracking-tight">{sw.home.title}</h1>
      {/* The version this device runs, to compare with the server's after an update (SPIKE-1).
          One string, not two pieces: React would put a marker between two pieces in the HTML. */}
      <p className="text-sm text-muted-foreground">{`${sw.home.version} ${APP_VERSION}`}</p>
    </main>
  );
}
