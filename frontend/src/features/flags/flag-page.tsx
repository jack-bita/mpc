// flag-page.tsx — one flag's own page, opened by tapping its line on Tofauti (CTRL-4, 02 §13), as Jack pictured it
// (24 Nov 2026): what happened in a sentence, who it names, where, which laptop and when, and everything written about
// it, oldest first. A flag about a tap opens that tap's day, where its pay is decided (ATT-6): deciding a day closes no
// flag (Jack: A). While it waits, three buttons, each a sheet: Eleza, Imetatuliwa and Si tatizo (flag-note.tsx); someone
// the flag names has Eleza alone, as they never close their own (02 §13).
//
// At /flags/view/?id=…, as the app has no [id] pages (ADR-0016): the page around it reads the id from the address. It
// asks GET /api/v1/control/flags/{id}/; one the person may not close is "not found", as another shop's is. The back
// arrow leads to the list, as it was left, or to the list when the page was opened from outside the app.
//
// "use client": it asks use-intl for words (use-client.test.ts), and calls the server.
"use client";

import { useQueryClient } from "@tanstack/react-query";
import { type ReactNode, useId, useRef, useState } from "react";
import { useTranslations } from "use-intl";

import { ApiErrorAlert } from "@/components/api-error-alert";
import { Alert, AlertDescription } from "@/components/design/alert";
import { Button, ButtonLink } from "@/components/design/button";
import { Card, CardContent } from "@/components/design/card";
import { PageHeader } from "@/components/design/page-header";
import {
  mayManageAttendance,
  monthOf,
} from "@/features/attendance/attendance-month";
import { workerMonthAddress } from "@/features/attendance/worker-month";
import { useWhoIsHere, type WhoIsHere } from "@/features/people/who-is-here";
import { codeMessage, useCodeWords } from "@/i18n/codes";

import { FlagNoteSheet } from "./flag-note";
import {
  type Flag,
  FLAG_ACTIONS,
  type FlagAction,
  type FlagNote,
  FLAGS,
  FLAGS_PAGE,
  useFlag,
  useKindWords,
  useMomentWords,
  useNames,
  waits,
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
          {/* A flag of its own: on another's page, as the browser's back and forward move the address, a sheet open on
              the last one closes, its words with it. */}
          <Actions key={flag.data.id} flag={flag.data} />
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

/** Eleza, Imetatuliwa and Si tatizo, each in a sheet, while the flag waits; and the line that says what one did. */
function Actions({ flag }: { flag: Flag }) {
  const t = useTranslations("flags.act");
  const codes = useCodeWords();
  const store = useQueryClient();
  const [open, setOpen] = useState<FlagAction | null>(null);
  // What the last one did, said on a line the keyboard goes to: after a close, the buttons are gone.
  const [done, setDone] = useState<string | null>(null);
  // Whether the last sheet ended in a change, read as it goes, which is after the draw that took it away: a ref, not
  // the state (worker-actions.tsx).
  const afterChange = useRef(false);
  const doneLine = useRef<HTMLDivElement>(null);
  const buttons = useRef(new Map<FlagAction, HTMLButtonElement>());
  const waiting = waits(flag);
  // One the flag names says why, and someone else closes it (02 §13): the server refuses theirs too.
  const offered: readonly FlagAction[] = !waiting
    ? []
    : flag.names_you
      ? ["explain"]
      : FLAG_ACTIONS;

  return (
    <div className="grid gap-4">
      {/* Always on the page, empty and hidden until something happens: Alert's role="status" is read when its words
          change, and one that comes with its words already in it may go unsaid (worker-actions.tsx). */}
      <div
        ref={doneLine}
        tabIndex={-1}
        className={done ? "outline-none" : "sr-only"}
      >
        <Alert kind="info">
          {done ? <AlertDescription>{done}</AlertDescription> : null}
        </Alert>
      </div>
      {waiting && flag.names_you ? <p>{t("namesYou")}</p> : null}
      {offered.length === 0 ? null : (
        <div className="flex flex-wrap gap-3">
          {offered.map((action) => (
            <Button
              key={action}
              ref={(button) => {
                if (button) buttons.current.set(action, button);
                else buttons.current.delete(action);
              }}
              // The main green for the way most end, Imetatuliwa; the other two beside it.
              kind={action === "resolve" ? "main" : "second"}
              size="normal"
              onClick={() => {
                afterChange.current = false;
                setDone(null);
                setOpen(action);
              }}
            >
              {t(`${action}.button`)}
            </Button>
          ))}
        </div>
      )}
      {/* Drawn only while open, so a sheet closed with Ghairi forgets what was typed. Open still when the flag is closed
          by someone else meanwhile, to say so; Ghairi then leaves a page with no buttons. */}
      {open === null ? null : (
        <FlagNoteSheet
          flag={flag}
          action={open}
          onDone={() => {
            afterChange.current = true;
            setOpen(null);
            setDone(t(`${open}.done`));
          }}
          onClose={() => {
            setOpen(null);
            if (waiting) {
              // Asked again: a send whose answer was lost may have moved the flag.
              void store.invalidateQueries({ queryKey: FLAGS });
              return;
            }
            // Closed while the sheet was open, by someone else, or by a send whose answer was lost: the buttons went,
            // so the page says why, on the line the keyboard goes to.
            afterChange.current = true;
            setDone(codeMessage(codes, "flag.closed"));
          }}
          // After a change, the done line; after Ghairi, the very button that opened it.
          finalFocus={() =>
            afterChange.current
              ? doneLine.current
              : (buttons.current.get(open) ?? null)
          }
        />
      )}
    </div>
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
