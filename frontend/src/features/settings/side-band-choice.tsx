// side-band-choice.tsx — Rangi, in each side's box on Mipangilio ya duka: the band the side shows under the top bar,
// and for someone holding settings.manage on it, Badilisha to pick another (SHOP-4).
//
// The band tells a worker at a glance which side a screen is for: blue, or white and faded red stripes, like the
// Foods bags (UI-8). The owner picks it the way he changes a rule above it: Badilisha opens the two bands, Hifadhi
// saves the one picked, Ghairi closes with nothing sent (Jack, 16 Nov 2026: the page works one way everywhere, and a
// thumb that brushes a row while scrolling changes nothing). No question before it: a colour changes no money and is
// undone the same way. Each band is shown in colour beside its word, so it never leans on the colour alone.
//
// PATCH /api/v1/shops/sides/{id}/ sends the band alone, with the side's version as it stood when the form opened, as
// the switch keeps what its question asked (side-switch.tsx): the page reads the sides again by itself when the phone
// comes back to it, and the version the owner saw is the one he decides on. Someone else's change since is refused
// (version_conflict), and the page reads the side again; on the demo every visitor shares one shop, so a band there
// answers demo.sides_fixed (Jack, SHOP-4). Each refusal shows in the side's box. The picked band the side already has
// sends nothing: no new version, and no change for the laptops to fetch.
//
// "use client": it asks use-intl for words (use-client.test.ts), and calls the server.
"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useTranslations } from "use-intl";

import { api } from "@/api/client";
import { answerOf, ApiRefusal } from "@/api/refusal";
import type { components } from "@/api/schema";
import { ApiErrorAlert } from "@/components/api-error-alert";
import { Button } from "@/components/design/button";
import { Choice } from "@/components/design/choice";
import { SIDE_BAND_LOOKS, SideBand } from "@/components/design/side-band";
import { DEVICE_CHECK } from "@/features/devices/device-check";
import { WHO_IS_HERE } from "@/features/people/who-is-here";
import { useOnline } from "@/offline/network";

import { keepTheSide, SIDES } from "./sides";

type Side = components["schemas"]["Side"];
type Band = Side["band"];

// The band as a small swatch: taller than under the bar, so a colour reads in a line of text.
const SWATCH = "h-3 w-16 rounded-sm";

export function SideBandChoice({
  side,
  mayChange,
}: {
  side: Side;
  mayChange: boolean;
}) {
  const t = useTranslations("shopSettings.sides");
  const form = useTranslations("shopSettings.form");
  const online = useOnline();
  const store = useQueryClient();
  // The open form: the band picked so far, and the side's version as it opened (see the top of this file). None while
  // the form is closed.
  const [open, setOpen] = useState<{ picked: Band; version: number } | null>(
    null,
  );
  // The side as the server last saved it here, said once in the status line (below).
  const [saved, setSaved] = useState<Side | null>(null);

  // Where the keyboard goes as the form closes: back to Badilisha, as the form's buttons are gone. Counted, so each
  // close moves it (side-switch.tsx).
  const opener = useRef<HTMLButtonElement>(null);
  const [closes, setCloses] = useState(0);
  useEffect(() => {
    if (closes > 0) opener.current?.focus();
  }, [closes]);
  function close() {
    setOpen(null);
    setCloses((count) => count + 1);
  }

  // As the form opens, the keyboard starts on the side's own band, as on a rule's yes or no (setting-form.tsx):
  // Choice, over Base UI's radios, takes no autoFocus, so the form finds the picked one itself, once.
  const choice = useRef<HTMLDivElement>(null);
  const isOpen = open !== null;
  useEffect(() => {
    if (!isOpen) return;
    choice.current
      ?.querySelector<HTMLElement>('[role="radio"][aria-checked="true"]')
      ?.focus();
  }, [isOpen]);

  const change = useMutation({
    // The band alone, with the version read as the form opened (see the top of this file).
    mutationFn: ({ band, version }: { band: Band; version: number }) =>
      answerOf(
        api.PATCH("/api/v1/shops/sides/{id}/", {
          params: { path: { id: side.id } },
          body: { band, version },
        }),
      ),
    onSuccess: (answer) => {
      keepTheSide(store, answer);
      // The bar above the page draws the band from elsewhere: in the office, from `me` (sideAt); before a login, from
      // the device's saved copy (device-check.tsx). Both are asked again, so the bar shows the new band at once, not
      // at the next page or the next 5-minute check (SHOP-4's review). A phone that is no device gets "not
      // registered" again, which it already was.
      void store.invalidateQueries({ queryKey: WHO_IS_HERE });
      void store.invalidateQueries({ queryKey: DEVICE_CHECK });
      setSaved(answer);
    },
    onError: (error) => {
      // Someone changed the side since the form opened: read it again, so the next try has its version and its band.
      if (error instanceof ApiRefusal && error.body.code === "version_conflict")
        void store.invalidateQueries({ queryKey: SIDES });
    },
    // Closed either way: a refusal shows in the box, and Badilisha opens the form again on the side as it is now.
    onSettled: close,
  });

  function save() {
    if (open === null) return;
    // The band the side has: nothing to send (see the top of this file).
    if (open.picked === side.band) {
      close();
      return;
    }
    change.mutate({ band: open.picked, version: open.version });
  }

  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        {/* Its word beside its colour, so it doesn't lean on the colour alone. */}
        <p className="flex flex-wrap items-center gap-x-3 text-lg">
          <span className="font-medium">{t("band")}</span>
          <SideBand look={side.band} className={SWATCH} />
          <span>{t(`looks.${side.band}`)}</span>
        </p>
        {mayChange && open === null ? (
          <Button
            ref={opener}
            kind="second"
            size="normal"
            // Names the side, as a list of the same word reads to a screen reader as nothing.
            aria-label={t("changeBandOf", { side: side.name })}
            disabled={!online}
            onClick={() => {
              setSaved(null);
              change.reset();
              setOpen({ picked: side.band, version: side.version });
            }}
          >
            {t("changeBand")}
          </Button>
        ) : null}
      </div>
      {open !== null ? (
        <div ref={choice} className="grid gap-3">
          <Choice
            label={t("bandOf", { side: side.name })}
            hint={t("bandHint")}
            options={SIDE_BAND_LOOKS.map((look) => ({
              value: look,
              label: t(`looks.${look}`),
              picture: <SideBand look={look} className={SWATCH} />,
            }))}
            value={open.picked}
            onValueChange={(picked) => {
              const band = SIDE_BAND_LOOKS.find((look) => look === picked);
              if (band) setOpen({ ...open, picked: band });
            }}
          />
          <div className="flex flex-wrap gap-3">
            {/* Switched off while it is sent, so a second tap sends nothing, and while offline, so nothing waits unsent
                while it looks done (setting-form.tsx). */}
            <Button
              size="normal"
              disabled={change.isPending || !online}
              onClick={save}
            >
              {form("save")}
            </Button>
            <Button
              kind="second"
              size="normal"
              // Off too while the band is on its way: it can't be called back, and a Ghairi then would only hide a
              // change that still goes through (side-switch.tsx).
              disabled={change.isPending}
              onClick={close}
            >
              {form("cancel")}
            </Button>
          </div>
        </div>
      ) : null}
      {/* In the side's box: on the demo, demo.sides_fixed; someone else's change, version_conflict. */}
      <ApiErrorAlert error={change.error} />
      {/* Always on the page, empty until a save: a role="status" line is read when its words change
          (offline-banner.tsx). */}
      <p role="status" className={saved ? "font-medium" : "sr-only"}>
        {saved ? t("bandSaved", { side: saved.name }) : null}
      </p>
    </div>
  );
}
