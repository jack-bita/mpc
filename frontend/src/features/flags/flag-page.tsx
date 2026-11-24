// flag-page.tsx — one flag's own page, opened by tapping its line on Tofauti (CTRL-4, 02 §13), as Jack pictured it
// (24 Nov 2026): what happened in a sentence, who it names, where, which laptop and when, and everything written about
// it, oldest first. A flag about a tap opens that tap's day, where its pay is decided (ATT-6): deciding a day closes no
// flag (Jack: A).
//
// At /flags/view/?id=…, as the app has no [id] pages (ADR-0016): the page around it reads the id from the address. It
// asks GET /api/v1/control/flags/{id}/; one the person may not close is "not found", as another shop's is. The back
// arrow leads to the list, as it was left, or to the list when the page was opened from outside the app.
//
// "use client": it asks use-intl for words (use-client.test.ts), and calls the server.
"use client";

import { type ReactNode, useId } from "react";
import { useTranslations } from "use-intl";

import { ApiErrorAlert } from "@/components/api-error-alert";
import { ButtonLink } from "@/components/design/button";
import { Card, CardContent } from "@/components/design/card";
import { PageHeader } from "@/components/design/page-header";
import {
  mayManageAttendance,
  monthOf,
} from "@/features/attendance/attendance-month";
import { workerMonthAddress } from "@/features/attendance/worker-month";
import { useWhoIsHere, type WhoIsHere } from "@/features/people/who-is-here";

import {
  type Flag,
  type FlagNote,
  FLAGS_PAGE,
  useFlag,
  useKindWords,
  useMomentWords,
  useNames,
} from "./flags";
import { useNoteWords, useWhatHappened } from "./flag-words";

export function FlagScreen({ id }: { id: string | null }) {
  const t = useTranslations("flags");
  // The PIN login's book, for its "Subiri kidogo…", which the office says the same way.
  const loginWords = useTranslations("login");
  const kindWords = useKindWords();
  const who = useWhoIsHere();
  // Asked here, in the part always on the page, and handed down as the flag itself (frontend rules).
  const flag = useFlag(id, who.data !== undefined);
  const waiting =
    who.isPending || (id !== null && who.data !== undefined && flag.isPending);

  return (
    <div className="grid max-w-2xl gap-6">
      {/* The flag's kind as the title, as its line on the list says it; until it comes, "Tofauti". */}
      <PageHeader
        title={flag.data ? kindWords(flag.data.kind) : t("title")}
        fallback={FLAGS_PAGE}
      />
      <p role="status" className={waiting ? "text-lg" : "sr-only"}>
        {waiting ? loginWords("waiting") : null}
      </p>
      {id === null ? <p>{t("page.noFlag")}</p> : null}
      {/* Not logged in ("Ingia kwanza"), no network, or the server's own problem. */}
      <ApiErrorAlert error={who.error} />
      {/* A failed read above the flag, not in its place: a refresh that fails keeps the flag last read on the screen. */}
      <ApiErrorAlert error={flag.error} />
      {who.data && flag.data ? (
        <>
          <WhatHappened flag={flag.data} me={who.data} />
          <Notes flag={flag.data} timezone={who.data.shop.timezone} />
        </>
      ) : null}
    </div>
  );
}

/** The flag's facts: the sentence, then each detail by its name; and the way to the day of the tap it is about. */
function WhatHappened({ flag, me }: { flag: Flag; me: WhoIsHere }) {
  const t = useTranslations("flags");
  const names = useNames();
  const happened = useWhatHappened();
  const moment = useMomentWords(me.shop.timezone);
  const { sentence, why } = happened(flag);

  return (
    <Card>
      <CardContent className="grid gap-4">
        <p className="text-lg">{sentence}</p>
        {why === null ? null : <p>{t("page.why", { why })}</p>}
        <dl className="grid gap-3">
          {flag.people.length === 0 ? null : (
            <Detail label={t("page.people", { count: flag.people.length })}>
              {names(flag.people)}
            </Detail>
          )}
          <Detail label={t("page.side")}>{flag.side ?? t("wholeShop")}</Detail>
          {flag.device === null ? null : (
            <Detail label={t("page.device")}>{flag.device}</Detail>
          )}
          {/* A record a rescue file brought (SYNC-12): made on one laptop, sent by another. */}
          {flag.brought_from === null ? null : (
            <Detail label={t("page.broughtFrom")}>{flag.brought_from}</Detail>
          )}
          {flag.loaded_by === null ? null : (
            <Detail label={t("page.loadedBy")}>{flag.loaded_by}</Detail>
          )}
          {/* By the laptop's clock, the only time its record has: said so, as that clock may be the very problem. */}
          {flag.made_at === null ? null : (
            <Detail label={t("page.madeAt")}>{moment(flag.made_at)}</Detail>
          )}
          <Detail label={t("page.raisedAt")}>{moment(flag.raised_at)}</Detail>
          <Detail label={t("page.status")}>{t(`status.${flag.status}`)}</Detail>
        </dl>
        {/* The tap's day, for whoever may fix attendance: the month's routes ask that key, which a person who may close
            flags need not hold. */}
        {flag.tap !== null && mayManageAttendance(me) ? (
          <div>
            <ButtonLink
              href={workerMonthAddress(
                flag.tap.staff,
                monthOf(flag.tap.day),
                flag.tap.day,
              )}
              kind="second"
              size="normal"
            >
              {t("page.openDay")}
            </ButtonLink>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

function Detail({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="font-semibold">{children}</dd>
    </div>
  );
}

/** Everything written about the flag, oldest first: each note's words, who wrote it and when. */
function Notes({ flag, timezone }: { flag: Flag; timezone: string }) {
  const t = useTranslations("flags");
  const id = useId();
  return (
    <section className="grid gap-3" aria-labelledby={id}>
      {/* Counted, so the manager sees at once whether anyone has said anything. */}
      <h2 id={id} className="text-lg font-semibold">
        {t("page.notes", { count: flag.notes.length })}
      </h2>
      {flag.notes.length === 0 ? (
        <p>{t("page.noNotes")}</p>
      ) : (
        <Card className="py-0">
          {/* role="list" written out: Safari with VoiceOver stops calling a <ul> a list once its bullets are styled away. */}
          <ul role="list" className="divide-y divide-border">
            {flag.notes.map((note) => (
              <li key={note.id} className="grid gap-1 px-4 py-3">
                <Note note={note} flag={flag} timezone={timezone} />
              </li>
            ))}
          </ul>
        </Card>
      )}
    </section>
  );
}

function Note({
  note,
  flag,
  timezone,
}: {
  note: FlagNote;
  flag: Flag;
  timezone: string;
}) {
  const t = useTranslations("flags");
  const moment = useMomentWords(timezone);
  const words = useNoteWords();
  return (
    <>
      <p>{words(note, flag)}</p>
      <p className="text-muted-foreground">
        {/* What it did: an explanation, or how it closed the flag; who wrote it, the system for a note of its own. */}
        {t("page.noteBy", {
          step: t(`status.${note.step}`),
          by: note.by ?? t("page.system"),
          when: moment(note.at),
        })}
      </p>
    </>
  );
}
