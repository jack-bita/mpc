// page.tsx — the home page at "/": on a new device, the Karibu welcome, with Ingia for a manager's own
// phone (UI-5) and the way to Sajili kifaa hiki for a new laptop (UI-3); on a registered one, the PIN
// login, and who is logged in (UI-4). The app's version on both.
//
// "use client": every page in this app is a client component (ADR-0016), because pages
// will read the device's own data (Dexie) and must work with no server. Next.js still
// renders the page once at build time, so out/index.html already holds the first HTML.
"use client";

import { useTranslations } from "use-intl";

import { ButtonLink } from "@/components/design/button";
import { useThisDevice } from "@/features/devices/this-device";
import { AtTheDevice } from "@/features/login/at-the-device";
import { APP_VERSION } from "@/lib/version";

export default function HomePage() {
  // The words come from the open book, Swahili or English (ADR-0040).
  const t = useTranslations("home");
  const register = useTranslations("device.register");
  const device = useThisDevice();
  // The version this device runs, to compare with the server's after an update (SPIKE-1).
  // The book places the number ("Toleo {version}"), so each language picks its own word order.
  // One string, not two pieces: React would put a marker between two pieces in the HTML.
  const version = (
    <p className="text-sm text-muted-foreground">
      {t("version", { version: APP_VERSION })}
    </p>
  );

  // A registered device: the PIN login, under the shop's top bar, which names the shop and the side
  // (UI-4). Built knowing no device (this-device.ts), so the static page holds the welcome below; a
  // registered device swaps it for the login at once.
  if (device) return <AtTheDevice device={device}>{version}</AtTheDevice>;

  // A new device: the welcome, and its two ways on. A manager's own phone never registers, and logs in
  // often: Ingia is the main button. A laptop registers once, and then opens on the PIN login instead.
  return (
    // min-h-svh: the full height of the phone's visible screen, browser bars excluded.
    <main className="flex min-h-svh flex-col items-center justify-center gap-4 p-4">
      <h1 className="text-4xl font-semibold tracking-tight">{t("title")}</h1>
      <ButtonLink href="/login/">{t("login")}</ButtonLink>
      <ButtonLink href="/register-device/" kind="second">
        {register("title")}
      </ButtonLink>
      {version}
    </main>
  );
}
