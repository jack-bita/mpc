// page.tsx — the home page at "/": for now, the Karibu welcome and the app's version.
//
// "use client": every page in this app is a client component (ADR-0016), because pages
// will read the device's own data (Dexie) and must work with no server. Next.js still
// renders the page once at build time, so out/index.html already holds the first HTML.
"use client";

import { useTranslations } from "use-intl";

import { APP_VERSION } from "@/lib/version";

export default function HomePage() {
  // The words come from the open book, Swahili or English (ADR-0040).
  const t = useTranslations("home");

  return (
    // min-h-svh: the full height of the phone's visible screen, browser bars excluded.
    <main className="flex min-h-svh flex-col items-center justify-center gap-2 p-4">
      <h1 className="text-4xl font-semibold tracking-tight">{t("title")}</h1>
      {/* The version this device runs, to compare with the server's after an update (SPIKE-1).
          The book places the number ("Toleo {version}"), so each language picks its own word order.
          One string, not two pieces: React would put a marker between two pieces in the HTML. */}
      <p className="text-sm text-muted-foreground">
        {t("version", { version: APP_VERSION })}
      </p>
    </main>
  );
}
