// my-settings.tsx — Mipangilio yangu: a person's own language and font, each changed with one tap (UI-9,
// ADR-0039, 03 §7.4). The page is app/(office)/my-settings/page.tsx.
//
// Only the person changes their own: the route names nobody, and changes whoever is logged in
// (PATCH /api/auth/me/settings/). Saved on the person, not on this browser, so the choice follows them to
// every device they log in at, and the next person at a shared laptop keeps their own.
//
// A tap saves at once, with no Hifadhi button, and sends only the choice tapped: the other is left as the
// server has it, so a second tab can't send back an old one. The server's answer goes into the store's
// `me`, which every screen reads to know who is here, so the app follows the new choice with no second
// call (the app's frames apply it, UI-9). While a change is on its way, its dot shows it already.
//
// An office screen, so it needs the internet: offline, the office frame says Inahitaji mtandao, and both
// choices are switched off, so no tap waits unsaved while it looks done.
//
// "use client": it asks use-intl for words, and the server who is here.
"use client";

import {
  useMutation,
  useMutationState,
  useQueryClient,
} from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { useTranslations } from "use-intl";

import { api } from "@/api/client";
import { answerOf, ApiRefusal } from "@/api/refusal";
import type { components } from "@/api/schema";
import { ApiErrorAlert } from "@/components/api-error-alert";
import { ButtonLink } from "@/components/design/button";
import { Choice } from "@/components/design/choice";
import {
  useWhoIsHere,
  WHO_IS_HERE,
  type WhoIsHere,
} from "@/features/people/who-is-here";
import { useOnline } from "@/offline/network";

type Change = components["schemas"]["OwnSettingsRequest"];
type Saved = components["schemas"]["OwnSettingsAnswer"];

/** One tap: the choice it changes, and whose it is, by the person's id when it was tapped. */
interface Tap {
  change: Change;
  person: string;
}

// The settings' changes in the store's list, so the screen can find every one still on its way.
const SAVE_SETTINGS = ["auth", "me", "settings"] as const;

export function MySettings() {
  const t = useTranslations("mySettings");
  // The PIN login's book, for its "Subiri kidogo…", which this screen says the same way.
  const loginWords = useTranslations("login");
  const me = useWhoIsHere();
  const online = useOnline();
  const store = useQueryClient();

  const save = useMutation({
    mutationKey: SAVE_SETTINGS,
    mutationFn: ({ change }: Tap): Promise<Saved> =>
      answerOf(api.PATCH("/api/auth/me/settings/", { body: change })),
    // Into `me`, for the person who tapped: never into the next person's answer. The changes wait in one
    // queue, a logout after them, so this lands before anyone else logs in (CHANGES_IN_ORDER), but the
    // check costs nothing and keeps it true if that ever changes.
    onSuccess: (saved, { person }) =>
      store.setQueryData<WhoIsHere>(WHO_IS_HERE, (here) =>
        here && here.user.id === person
          ? { ...here, user: { ...here.user, ...saved } }
          : here,
      ),
  });
  // Every tap still on its way, oldest first: a font and then a language, tapped quickly, wait one after
  // the other, and both dots show what was tapped meanwhile, not only the last one.
  const onTheirWay = useMutationState({
    filters: { mutationKey: SAVE_SETTINGS, status: "pending" },
    select: (sending) => (sending.state.variables as Tap).change,
  });

  // Focus on the heading as the screen opens: the button that had it, on the home page, is gone, and a
  // screen reader then says where the person is (as office-home.tsx does).
  const heading = useRef<HTMLHeadingElement>(null);
  const arrived = me.data?.staff.id;
  useEffect(() => heading.current?.focus(), [arrived]);

  // A refusal is read before the answer, as on the office's home page: TanStack keeps the last answer
  // beside it, which would show the choices of someone the server has just refused. The office frame
  // says why, or sends them to the way in (office-frame.tsx).
  const refused = me.error instanceof ApiRefusal && me.error.status < 500;
  const here = refused ? undefined : me.data;
  // Until `me` first answers, "Subiri kidogo…", never a blank page (office-home.tsx).
  const waiting = me.isPending && me.failureCount === 0;

  // The status line's words: waiting for `me`, a change on its way, or the last one saved. Always on the
  // page, only its words change, as one that comes with its words in it often goes unsaid
  // (offline-banner.tsx).
  const status = waiting
    ? loginWords("waiting")
    : onTheirWay.length > 0
      ? t("saving")
      : save.isSuccess
        ? t("saved")
        : null;

  return (
    <div className="grid max-w-md gap-6">
      <p role="status" className={status ? "text-lg" : "sr-only"}>
        {status}
      </p>
      {here ? theChoices(here) : <ApiErrorAlert error={me.error} />}
    </div>
  );

  // Called, not drawn as a component of its own, so the heading keeps its place, and its focus, across
  // redraws (office-home.tsx).
  function theChoices(here: WhoIsHere) {
    // What the dots show: what the server has saved, with every tap still on its way laid over it.
    const shown: Saved = Object.assign(
      { language: here.user.language, font: here.user.font },
      ...onTheirWay,
    );
    const tap = (change: Change) =>
      save.mutate({ change, person: here.user.id });

    return (
      <>
        <h1
          ref={heading}
          tabIndex={-1}
          className="text-2xl font-semibold outline-none"
        >
          {t("title")}
        </h1>
        <p>{t("intro")}</p>
        {/* Each language named in that language, as the bar's button names it: someone who can't read
            the open one still finds their own (language-button.tsx). */}
        <Choice
          label={t("language")}
          options={[
            { value: "sw", label: t("languages.sw"), lang: "sw" },
            { value: "en", label: t("languages.en"), lang: "en" },
          ]}
          value={shown.language}
          onValueChange={(language) =>
            tap({ language: language as Change["language"] })
          }
          disabled={!online}
        />
        {/* Each font's row in that font, so a person sees what they pick (ADR-0039). */}
        <Choice
          label={t("font")}
          options={[
            { value: "default", label: t("fonts.default"), font: "default" },
            { value: "second", label: t("fonts.second"), font: "second" },
          ]}
          value={shown.font}
          onValueChange={(font) => tap({ font: font as Change["font"] })}
          disabled={!online}
        />
        {/* A change the server refused, as a suspension since the screen opened: why. Its dot is back
            on what is saved. */}
        <ApiErrorAlert error={save.error} />
        <div>
          {/* Back to the home page the person came from: the PIN screen's welcome at a shared device,
              where a PIN's session names its device; the office's home page for a password's. */}
          <ButtonLink
            href={here.device ? "/" : "/office/"}
            kind="second"
            size="normal"
          >
            {t("back")}
          </ButtonLink>
        </div>
      </>
    );
  }
}
