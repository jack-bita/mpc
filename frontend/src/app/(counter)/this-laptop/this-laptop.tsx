// this-laptop.tsx — the Kompyuta hii screen (SYNC-12, 03 §6.7): what keeps the shop's records safe on this
// laptop. It owns how both answers of keep-data.ts are shown: whether the browser keeps the data for good,
// and whether the app is installed, with a button or the menu's steps to install it. Under them, the rescue
// of a dying laptop's unsent records, in a file (rescue.tsx).
//
// A counter screen: it reads only what the browser says on this laptop, never the server, so it works the
// same offline (rule 5, ADR-0019). The counter's frame shows it only to someone logged in.
//
// "use client": it asks use-intl for words, and reads the browser's answers, in the browser only.
"use client";

import { useEffect } from "react";
import { useTranslations } from "use-intl";

import { Alert, AlertDescription } from "@/components/design/alert";
import { Button, ButtonLink } from "@/components/design/button";
import { askToKeepData, install, useKeepData } from "@/offline/keep-data";

import { Rescue } from "./rescue";

export function ThisLaptopScreen() {
  const t = useTranslations("thisLaptop");
  const { kept, install: installState } = useKeepData();

  // Asked again as the page opens: the answer may have changed since the app opened, as a laptop that
  // installed the app since gets a yes. Asking again costs nothing (keep-data.ts).
  useEffect(() => {
    void askToKeepData();
  }, []);

  return (
    <div className="grid max-w-md gap-6">
      <div>
        <ButtonLink href="/" kind="second" size="normal">
          {t("back")}
        </ButtonLink>
      </div>
      <h1 className="text-3xl font-semibold">{t("title")}</h1>

      <section className="grid gap-3">
        <h2 className="text-xl font-semibold">{t("keep.title")}</h2>
        {/* Nothing while the browser answers: a "not kept" that is only "not asked yet" would alarm. */}
        {kept === "kept" && <p>{t("keep.kept")}</p>}
        {/* Not kept: the danger kind, as the browser may wipe unsent records by itself. */}
        {(kept === "not_kept" || kept === "cannot_ask") && (
          <Alert kind="danger">
            <AlertDescription>
              {t(kept === "not_kept" ? "keep.notKept" : "keep.cannotAsk")}
            </AlertDescription>
          </Alert>
        )}
      </section>

      <section className="grid gap-3">
        <h2 className="text-xl font-semibold">{t("install.title")}</h2>
        {installState.kind === "installed" && <p>{t("install.installed")}</p>}
        {installState.kind === "offered" && (
          <div>
            <Button
              size="normal"
              onClick={() => void install(installState.offer)}
            >
              {t("install.button")}
            </Button>
          </div>
        )}
        {/* No offer from the browser: it was used already, dismissed, or this browser makes none. The
            browser's menu installs all the same. */}
        {installState.kind === "steps" && <p>{t("install.steps")}</p>}
      </section>

      <Rescue />
    </div>
  );
}
