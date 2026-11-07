// page.tsx — the home page at "/": the Karibu welcome, which device this is, and the app's version.
//
// A device not yet registered gets the way to Sajili kifaa hiki (UI-3); a registered one shows its name
// and its shop. UI-4 turns this page into the PIN login on a registered device.
//
// "use client": every page in this app is a client component (ADR-0016), because pages
// will read the device's own data (Dexie) and must work with no server. Next.js still
// renders the page once at build time, so out/index.html already holds the first HTML.
"use client";

import { useTranslations } from "use-intl";

import { ButtonLink } from "@/components/design/button";
import { useThisDevice } from "@/features/devices/this-device";
import { APP_VERSION } from "@/lib/version";

export default function HomePage() {
  // The words come from the open book, Swahili or English (ADR-0040).
  const t = useTranslations("home");
  const register = useTranslations("device.register");
  const device = useThisDevice();

  return (
    // min-h-svh: the full height of the phone's visible screen, browser bars excluded.
    <main className="flex min-h-svh flex-col items-center justify-center gap-4 p-4">
      <h1 className="text-4xl font-semibold tracking-tight">{t("title")}</h1>
      {/* The name on the manager's list and the shop's, or the way to register. Built knowing no
          device (this-device.ts), so the static page holds the link; a registered device swaps it
          for its name at once. */}
      {device ? (
        <p className="text-lg">
          {t("thisDevice", { device: device.name, shop: device.shop.name })}
        </p>
      ) : (
        <ButtonLink href="/register-device/">{register("title")}</ButtonLink>
      )}
      {/* The version this device runs, to compare with the server's after an update (SPIKE-1).
          The book places the number ("Toleo {version}"), so each language picks its own word order.
          One string, not two pieces: React would put a marker between two pieces in the HTML. */}
      <p className="text-sm text-muted-foreground">
        {t("version", { version: APP_VERSION })}
      </p>
    </main>
  );
}
