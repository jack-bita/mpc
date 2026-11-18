// worker-form.tsx — Ongeza: a new worker joins the shop (PPL-6, PPL-4). Opens under Ongeza on Wafanyakazi.
//
// Four boxes: Jina kamili, the person's whole name, as the PIN tiles show it without a photo (02 §5); Jina la kuitwa,
// the nickname the shop calls them by, on every laptop and every record; Kazi, a job title, which may be empty, as
// many workers have no title beyond their role; and Siku ya kwanza, the first day of work.
//
// The first day starts at the shop's today, as most workers are added the morning they start. The server takes any
// date (PPL-4's review): a worker added late, or one starting next month. So a day more than 30 days before or after
// today is asked about once, beside the box, and the next Hifadhi with the same day sends it (a default of the card):
// a year typed wrong, 2025 for 2026, would start every pay and attendance count in the wrong place.
//
// What the form can see itself is said at once, in the server's own sentences, and nothing is sent: an empty name or
// nickname (`blank`), an empty first day (`required`). The server checks the rest. A nickname another current worker
// has (staff.display_name_taken) is the whole request's code, as the database's rule is of lower(display_name), no
// field (PPL-4); it shows beside Jina la kuitwa all the same, where the owner fixes it.
//
// The id is sent again with every try of the same boxes (ADR-0007): a send whose answer the network lost, tried again,
// gets the stored worker back, not a second Juma. A changed box gets a new id, as the server answers a repeated id
// with the worker it stored, whatever the new send carries (closure-form.tsx).
//
// No phone (PPL-10), role (PPL-7) or PIN (PPL-8) yet: a new worker can't log in until those cards, which the screen
// says once he is added.
//
// "use client": it asks use-intl for words (use-client.test.ts), and calls the server.
"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useRef, useState } from "react";
import { useTranslations } from "use-intl";

import { api } from "@/api/client";
import { useApiErrorWords } from "@/api/errors";
import { answerOf, ApiRefusal } from "@/api/refusal";
import { ApiErrorAlert } from "@/components/api-error-alert";
import { Button } from "@/components/design/button";
import { Field } from "@/components/design/field";
import { aboutTheWholeRequest } from "@/features/settings/closures";
import { codeMessage, useCodeWords } from "@/i18n/codes";
import { formatDay } from "@/lib/format";
import { newId } from "@/lib/ids";
import { useOnline } from "@/offline/network";

import { keepWorker, type Worker, WORKERS } from "./workers";

/** How far from today a first day may be before the form asks once more: about a month, either way. */
const FAR_DAYS = 30;

/** The whole request's code the server sends for a nickname taken, shown beside Jina la kuitwa (see the top). */
const NICKNAME_TAKEN = "staff.display_name_taken";

/** The form's own checks, by box, as the codes the server would send. */
type Checks = {
  full_name?: string;
  display_name?: string;
  started_on?: string;
};

/** The days from one day to another, "2026-11-02" to "2026-11-18" is 16: both read at midnight UTC, so no clock
 * change between them moves the count. */
function daysBetween(from: string, to: string): number {
  return (Date.parse(to) - Date.parse(from)) / 86_400_000;
}

export function WorkerForm({
  today,
  onSaved,
  onCancel,
}: {
  /** The shop's today, in its own time zone: where the first day's box starts. */
  today: string;
  onSaved: (worker: Worker) => void;
  onCancel: () => void;
}) {
  const t = useTranslations("workers.form");
  const codes = useCodeWords();
  const { fieldMessages } = useApiErrorWords();
  const online = useOnline();
  const store = useQueryClient();

  // The last send: its id, and what it carried, so a try of the same keeps its id (see the top of this file).
  const lastSend = useRef<{ id: string; carried: string } | null>(null);
  const [fullName, setFullName] = useState("");
  const [nickname, setNickname] = useState("");
  const [jobTitle, setJobTitle] = useState("");
  const [firstDay, setFirstDay] = useState(today);
  const [own, setOwn] = useState<Checks>({});
  // The far first day the form has asked about: Hifadhi again with this same day sends it.
  const [askedAbout, setAskedAbout] = useState<string | null>(null);

  const save = useMutation({
    mutationFn: (body: {
      id: string;
      full_name: string;
      display_name: string;
      job_title: string;
      started_on: string;
    }) => answerOf(api.POST("/api/v1/people/staff/", { body })),
    onSuccess: (worker) => {
      // At the top of the list at once, newest first, then the list asks again (workers.ts).
      keepWorker(store, worker);
      void store.invalidateQueries({ queryKey: WORKERS });
      onSaved(worker);
    },
  });

  function send(event: FormEvent) {
    // The browser would send the form itself and load a new page; the app sends it instead.
    event.preventDefault();
    // The last send's refusal is about what was sent then: each tap shows only what it finds (setting-form.tsx).
    save.reset();
    // As the server keeps them: the spaces around each taken off, so spaces alone are no name.
    const full = fullName.trim();
    const called = nickname.trim();
    const title = jobTitle.trim();
    const checks: Checks = {};
    if (full === "") checks.full_name = "blank";
    if (called === "") checks.display_name = "blank";
    if (firstDay === "") checks.started_on = "required";
    setOwn(checks);
    if (Object.keys(checks).length > 0) return;
    // A day far from today: asked about once, beside its box; the same day again is the owner's answer.
    const far = Math.abs(daysBetween(today, firstDay)) > FAR_DAYS;
    if (far && askedAbout !== firstDay) {
      setAskedAbout(firstDay);
      return;
    }
    // The same id for a try of the same boxes; a new one once any of them changed.
    const carried = JSON.stringify([full, called, title, firstDay]);
    if (lastSend.current?.carried !== carried)
      lastSend.current = { id: newId(), carried };
    save.mutate({
      id: lastSend.current.id,
      full_name: full,
      display_name: called,
      job_title: title,
      started_on: firstDay,
    });
  }

  // Where each refusal shows: beside its box, the form's own first, then the server's. The nickname taken, the whole
  // request's code, beside Jina la kuitwa too, and so not again above the buttons.
  const byField = fieldMessages(save.error);
  const said = (code?: string) =>
    code === undefined ? undefined : codeMessage(codes, code);
  const nicknameTaken =
    save.error instanceof ApiRefusal && save.error.body.code === NICKNAME_TAKEN;
  const askingAboutTheDay =
    askedAbout !== null &&
    askedAbout === firstDay &&
    own.started_on === undefined;

  return (
    // noValidate: the browser's own checks would speak its language, not the shop's.
    <form noValidate onSubmit={send} className="grid gap-6">
      <Field
        label={t("fullName")}
        hint={t("fullNameHint")}
        error={said(own.full_name) ?? byField.full_name}
        value={fullName}
        onChange={(event) => setFullName(event.target.value)}
        autoComplete="off"
        // As the server keeps it (User.full_name, 150 characters).
        maxLength={150}
        // The person just asked for this form: the keyboard starts in its first box, where Ongeza was.
        autoFocus
      />
      <Field
        label={t("nickname")}
        hint={t("nicknameHint")}
        error={
          said(own.display_name) ??
          (nicknameTaken ? said(NICKNAME_TAKEN) : undefined) ??
          byField.display_name
        }
        value={nickname}
        onChange={(event) => setNickname(event.target.value)}
        autoComplete="off"
        // As the server keeps it (StaffMember.display_name, 40 characters).
        maxLength={40}
      />
      <Field
        label={t("jobTitle")}
        hint={t("jobTitleHint")}
        error={byField.job_title}
        value={jobTitle}
        onChange={(event) => setJobTitle(event.target.value)}
        autoComplete="off"
        // As the server keeps it (StaffMember.job_title, 60 characters).
        maxLength={60}
      />
      <div className="grid gap-2">
        <Field
          label={t("firstDay")}
          hint={t("firstDayHint")}
          error={said(own.started_on) ?? byField.started_on}
          type="date"
          value={firstDay}
          onChange={(event) => setFirstDay(event.target.value)}
        />
        {/* The question about a far day, under its box: in words, not in red, as it is a question, not a refusal.
            On the page from the start, empty, and read by a screen reader when its words come: a role="status" line
            that comes with its words in it often goes unsaid (offline-banner.tsx). */}
        <p role="status" className="font-semibold">
          {askingAboutTheDay ? t("farDay", { day: formatDay(firstDay) }) : null}
        </p>
      </div>
      {/* What no box names: an id another shop holds, no network, no key, the server's own problem. */}
      <ApiErrorAlert
        error={nicknameTaken ? null : aboutTheWholeRequest(save.error)}
      />
      <div className="flex flex-wrap gap-3">
        {/* Switched off while it is sent, so a second tap sends nothing, and while offline, so nothing waits unsent
            while it looks done (setting-form.tsx); the id would save it once anyway. */}
        <Button type="submit" disabled={save.isPending || !online}>
          {t("save")}
        </Button>
        <Button kind="second" onClick={onCancel}>
          {t("cancel")}
        </Button>
      </div>
    </form>
  );
}
