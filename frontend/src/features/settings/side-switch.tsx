// side-switch.tsx — Pande, at the bottom of Mipangilio ya duka: each side the person sees, switched on or off,
// and for someone holding settings.manage on it, the switch (SHOP-5, ADR-0033).
//
// A side switched off isn't used at the shop's laptops: a new side starts off, and reaches the counters only once
// the owner agrees to start using it (SHOP-2, ADR-0033). So a wrong tap matters: the switch asks first, both ways
// (Jack, 15 Nov 2026: the card's Done when asks for a confirm on or off), with Hapana as the button that has the
// keyboard, so an Enter pressed by mistake changes nothing.
//
// PATCH /api/v1/shops/sides/{id}/ sends the switch alone, with the side's version as this page read it: the server
// refuses it if someone changed the side since (version_conflict), and then the page reads the side again, so the
// next try sends the new version. The question keeps what it asked as it opened, the side's new state and the version
// read then, and sends exactly that: the page reads the sides again by itself when the phone comes back to it, and a
// question that followed that read could turn "Zima?" into "Washa?" under the owner's thumb, with the new version,
// which the server would accept (SHOP-5's review). A name and the switch go one at a time (SideEditSerializer). On the demo every
// visitor shares one shop, so its sides stay as the seed made them, and a switch there answers demo.sides_fixed
// (SHOP-3's review): each refusal shows beside the switch it is about.
//
// GET /api/v1/shops/sides/ comes in pages of 50 (CursorPage): far more sides than a shop has, so the first page
// is all of them. In the sides' order by letter (Dawa's D before Vyakula's F), as the rules' lines are.
//
// "use client": it asks use-intl for words (use-client.test.ts), and calls the server.
"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useId, useRef, useState } from "react";
import { useTranslations } from "use-intl";

import { api } from "@/api/client";
import { answerOf, ApiRefusal } from "@/api/refusal";
import type { components } from "@/api/schema";
import { ApiErrorAlert } from "@/components/api-error-alert";
import { Button } from "@/components/design/button";
import { sidesWhere, type WhoIsHere } from "@/features/people/who-is-here";
import { cn } from "@/lib/utils";
import { useOnline } from "@/offline/network";

type Side = components["schemas"]["Side"];

/** The sides' place in the store of server answers. */
export const SIDES = ["shops", "sides"] as const;

/** The key that switches a side: changing the shop itself is one of the owner's own four (spec §6). */
const SWITCHES_SIDES = "settings.manage";

export function SideSwitches({ me }: { me: WhoIsHere }) {
  const t = useTranslations("shopSettings.sides");
  const sides = useQuery({
    queryKey: SIDES,
    queryFn: () => answerOf(api.GET("/api/v1/shops/sides/")),
    select: (page) =>
      [...page.results].sort((one, other) =>
        one.code.localeCompare(other.code),
      ),
  });
  // Where the person may switch: each side where they hold the key, on the whole shop counted on every side.
  const mayChange = new Set(
    sidesWhere(me, SWITCHES_SIDES).map((side) => side.id),
  );

  return (
    <section aria-labelledby="area-sides" className="grid gap-4">
      <div className="grid gap-2">
        <h2 id="area-sides" className="text-xl font-semibold">
          {t("title")}
        </h2>
        <p className="text-muted-foreground">{t("intro")}</p>
      </div>
      {/* A failed read shows above the sides, and keeps the last answer under it, as on the rules. */}
      <ApiErrorAlert error={sides.error} />
      {sides.data ? (
        // role="list" written out, for Safari with VoiceOver (device-list.tsx).
        <ul role="list" className="grid gap-4">
          {sides.data.map((side) => (
            <li key={side.id}>
              <SideSwitch side={side} mayChange={mayChange.has(side.id)} />
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

/** One side: its name, whether it is on, and for whoever may, the switch with its question. */
export function SideSwitch({
  side,
  mayChange,
}: {
  side: Side;
  mayChange: boolean;
}) {
  const t = useTranslations("shopSettings.sides");
  const online = useOnline();
  const store = useQueryClient();
  // What the open question asks, from the moment it opened: the side's new state, and the version read then. None
  // while no question is open.
  const [asked, setAsked] = useState<Pick<Side, "is_live" | "version"> | null>(
    null,
  );
  // The question's id, which both its answers name (aria-describedby): the keyboard lands on Hapana, and a screen
  // reader then says the question with it, not "Hapana, button" alone, as the question is what the confirm is for
  // (SHOP-5's review).
  const question = useId();
  // What the last switch did, said once in the status line (below).
  const [switched, setSwitched] = useState<Side | null>(null);

  // Where the keyboard goes when the question closes: back to the switch, as the question's buttons are gone.
  // Counted, so each close moves it (devices-screen.tsx).
  const opener = useRef<HTMLButtonElement>(null);
  const [closes, setCloses] = useState(0);
  useEffect(() => {
    if (closes > 0) opener.current?.focus();
  }, [closes]);
  function closeTheQuestion() {
    setAsked(null);
    setCloses((count) => count + 1);
  }

  const flip = useMutation({
    // The switch alone, with the version this page read (see the top of this file).
    mutationFn: ({ is_live, version }: Pick<Side, "is_live" | "version">) =>
      answerOf(
        api.PATCH("/api/v1/shops/sides/{id}/", {
          params: { path: { id: side.id } },
          body: { is_live, version },
        }),
      ),
    onSuccess: (saved) => {
      // The list holds the answer at once, with its new version, so a second switch sends that one.
      store.setQueryData<components["schemas"]["PaginatedSideList"]>(
        SIDES,
        (page) =>
          page && {
            ...page,
            results: page.results.map((each) =>
              each.id === saved.id ? saved : each,
            ),
          },
      );
      setSwitched(saved);
    },
    onError: (error) => {
      // Someone changed the side since this page read it: read it again, so the next try has its version.
      if (error instanceof ApiRefusal && error.body.code === "version_conflict")
        void store.invalidateQueries({ queryKey: SIDES });
    },
    onSettled: closeTheQuestion,
  });

  const label = side.is_live
    ? t("switchOffOf", { side: side.name })
    : t("switchOnOf", { side: side.name });

  return (
    <div className="grid gap-3 rounded-lg border border-input p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="flex flex-wrap gap-x-4 text-lg">
          <span className="font-semibold">{side.name}</span>
          {/* In words, and in colour beside them, so it doesn't lean on the colour alone. */}
          <span
            className={cn(
              "font-medium",
              side.is_live ? "text-primary" : "text-muted-foreground",
            )}
          >
            {side.is_live ? t("on") : t("off")}
          </span>
        </p>
        {mayChange && asked === null ? (
          <Button
            ref={opener}
            // Switching off is the one that stops a side at the counters: the warning colour says so.
            kind={side.is_live ? "danger" : "main"}
            size="normal"
            // Starts with the word on the button, and names the side, as a list of the same word reads to a
            // screen reader as nothing.
            aria-label={label}
            disabled={!online}
            onClick={() => {
              setSwitched(null);
              flip.reset();
              setAsked({ is_live: !side.is_live, version: side.version });
            }}
          >
            {side.is_live ? t("switchOff") : t("switchOn")}
          </Button>
        ) : null}
      </div>
      {asked !== null ? (
        <div className="grid gap-3">
          {/* Its words from what it asks, never from the side as the page has it now (see the top of this file). */}
          <p id={question} className="text-lg">
            {asked.is_live
              ? t("askOn", { side: side.name })
              : t("askOff", { side: side.name })}
          </p>
          <div className="flex flex-wrap gap-3">
            <Button
              kind={asked.is_live ? "main" : "danger"}
              size="normal"
              aria-describedby={question}
              // Switched off while it is sent, so a second tap sends nothing.
              disabled={flip.isPending || !online}
              onClick={() => flip.mutate(asked)}
            >
              {asked.is_live ? t("yesOn") : t("yesOff")}
            </Button>
            {/* The keyboard starts here, on the answer that changes nothing (see the top of this file). */}
            <Button
              kind="second"
              size="normal"
              aria-describedby={question}
              autoFocus
              onClick={closeTheQuestion}
            >
              {t("no")}
            </Button>
          </div>
        </div>
      ) : null}
      {/* Beside the switch it is about: on the demo, demo.sides_fixed; someone else's change, version_conflict. */}
      <ApiErrorAlert error={flip.error} />
      {/* Always on the page, empty until a switch: a role="status" line is read when its words change
          (offline-banner.tsx). */}
      <p role="status" className={switched ? "font-medium" : "sr-only"}>
        {switched
          ? switched.is_live
            ? t("switchedOn", { side: switched.name })
            : t("switchedOff", { side: switched.name })
          : null}
      </p>
    </div>
  );
}
