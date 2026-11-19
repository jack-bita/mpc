// worker-form.tsx — Ongeza: a new worker joins the shop (PPL-6, PPL-4). Opens under Ongeza on Wafanyakazi. And Mwajiri
// tena (PPL-11): the same boxes, for a worker who left and is hired again, opened on his old job's page (`again`).
//
// Five boxes: Jina kamili, the person's whole name, as the PIN tiles show it without a photo (02 §5); Jina la kuitwa,
// the nickname the shop calls them by, on every laptop and every record; Kazi, a job title, which may be empty, as
// many workers have no title beyond their role; Siku ya kwanza, the first day of work; and Simu, their phone, which
// may be empty (PPL-11), sent as typed for the server to store in its one form, and off on the demo, where no worker
// gets one, with the server's own sentence saying why in place of its hint (demo.phones_fixed, PPL-10).
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
// No role here: one is given on the worker's own page, with Ongeza kazi (PPL-8). No PIN yet (PPL-12): a new worker
// can't log in at a laptop until he has one, which the screen says once he is added.
//
// Mwajiri tena: Baraka left on 12 March and comes back. He is the same person, so he keeps his own full name, and the
// form has no Jina kamili box (Badilisha fixes it); his nickname and job title start as his old job's, and the first day
// at today. The old job's id goes with the new job's own (`hire_again`), and the server gives the same person a new job.
// A first day before his last day is said at once (staff.back_before_left); the server says it too when a later job of
// his ended after it. Another manager who hired him first: the server's staff.already_member above the buttons; Ghairi
// reads the worker again (worker-actions.tsx), and his old page then links to the new one.
//
// And from Ongeza itself: Baba, who forgot Baraka worked here, types him in as new, with his phone. The server makes
// nobody and names Baraka's old job (staff.left_here, with his full name and last day), and under Simu the form says
// whose phone it is, with Mwajiri tena: a question in words, not a refusal in red, as Baba did nothing wrong. Tapped,
// it hires Baraka again with the boxes already typed, his old job named, and neither his full name nor his phone sent,
// as the person keeps his own. The form keeps whom the phone found until Simu changes, not only while the server's
// answer is on show (the review): a hire again whose answer the network lost keeps its Mwajiri tena, which sends the
// same id again and so gets the job the first made, never a second Baraka; a phone typed anew forgets him. A phone
// anyone else has is only `unique` beside Simu: never whose (the server's rule).
//
// "use client": it asks use-intl for words (use-client.test.ts), and calls the server.
"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useRef, useState } from "react";
import { useTranslations } from "use-intl";

import { api } from "@/api/client";
import type { components } from "@/api/schema";
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

/** The server's code for the phone of a worker who left here, which names his old job (see the top). */
const LEFT_HERE = "staff.left_here";

/** The server's code for a phone sent on the demo, shown beside Simu if the box was on (see the top). */
const NO_PHONE_ON_DEMO = "demo.phones_fixed";

/** A job that ended, whose person is hired again: its id, and its last day, before which the new job can't start. */
type OldJob = { id: string; left_on: string };

/** The old job the server named for a phone typed on Ongeza (staff.left_here), with whose it is; else null. */
function foundBy(error: unknown): (OldJob & { name: string }) | null {
  if (!(error instanceof ApiRefusal) || error.body.code !== LEFT_HERE)
    return null;
  const { staff, full_name, left_on } = error.body.params;
  return typeof staff === "string" &&
    typeof full_name === "string" &&
    typeof left_on === "string"
    ? { id: staff, name: full_name, left_on }
    : null;
}

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
  again,
  demo = false,
  onSaved,
  onCancel,
}: {
  /** The shop's today, in its own time zone: where the first day's box starts. */
  today: string;
  /** Mwajiri tena: the job that ended, whose person is hired again (see the top). None for a new worker. */
  again?: Worker;
  /** This is the demo, where no worker gets a phone: Simu is off. */
  demo?: boolean;
  onSaved: (worker: Worker) => void;
  onCancel: () => void;
}) {
  const t = useTranslations("workers.form");
  const actions = useTranslations("workers.actions");
  const titles = useTranslations("workers.actions.title");
  const codes = useCodeWords();
  const { fieldMessages } = useApiErrorWords();
  const online = useOnline();
  const store = useQueryClient();

  // The last send: its id, and what it carried, so a try of the same keeps its id (see the top of this file).
  const lastSend = useRef<{ id: string; carried: string } | null>(null);
  const [fullName, setFullName] = useState("");
  const [nickname, setNickname] = useState(again?.display_name ?? "");
  const [jobTitle, setJobTitle] = useState(again?.job_title ?? "");
  const [firstDay, setFirstDay] = useState(today);
  const [phone, setPhone] = useState("");
  // Whom the phone found, a worker who left here (staff.left_here): kept until Simu changes (see the top).
  const [found, setFound] = useState<(OldJob & { name: string }) | null>(null);
  const [own, setOwn] = useState<Checks>({});
  // The far first day the form has asked about: Hifadhi again with this same day sends it.
  const [askedAbout, setAskedAbout] = useState<string | null>(null);

  const save = useMutation({
    mutationFn: (body: components["schemas"]["StaffAddRequest"]) =>
      answerOf(api.POST("/api/v1/people/staff/", { body })),
    onSuccess: (worker) => {
      // At the top of the list at once, newest first, then the list asks again (workers.ts): for one hired again,
      // his old job's link to the new one with it.
      keepWorker(store, worker);
      void store.invalidateQueries({ queryKey: WORKERS });
      onSaved(worker);
    },
    onError: (error) => {
      // The phone found a worker who left: kept, so a later refusal or a lost answer doesn't take Mwajiri tena away.
      const named = foundBy(error);
      if (named !== null) setFound(named);
    },
  });

  function send(event: FormEvent) {
    // The browser would send the form itself and load a new page; the app sends it instead.
    event.preventDefault();
    go(again ? { id: again.id, left_on: again.left_on ?? "" } : undefined);
  }

  /** Hifadhi: a new worker, or, with `old`, its person hired again (from the page, or the job a phone found). */
  function go(old: OldJob | undefined) {
    // The last send's refusal is about what was sent then: each tap shows only what it finds (setting-form.tsx).
    save.reset();
    // As the server keeps them: the spaces around each taken off, so spaces alone are no name.
    const full = fullName.trim();
    const called = nickname.trim();
    const title = jobTitle.trim();
    const typedPhone = phone.trim();
    const checks: Checks = {};
    if (old === undefined && full === "") checks.full_name = "blank";
    if (called === "") checks.display_name = "blank";
    if (firstDay === "") checks.started_on = "required";
    // Days as text sort as days do. The same day may: a leaving marked by mistake is mended at once.
    else if (old !== undefined && firstDay < old.left_on)
      checks.started_on = "staff.back_before_left";
    setOwn(checks);
    if (Object.keys(checks).length > 0) return;
    // A day far from today: asked about once, beside its box; the same day again is the owner's answer.
    const far = Math.abs(daysBetween(today, firstDay)) > FAR_DAYS;
    if (far && askedAbout !== firstDay) {
      setAskedAbout(firstDay);
      return;
    }
    // The same id for a try of the same boxes; a new one once any of them changed, or a hire again took its place.
    const carried = JSON.stringify([
      old?.id,
      full,
      called,
      title,
      firstDay,
      typedPhone,
    ]);
    if (lastSend.current?.carried !== carried)
      lastSend.current = { id: newId(), carried };
    const job = {
      id: lastSend.current.id,
      display_name: called,
      job_title: title,
      started_on: firstDay,
    };
    // Hired again: the old job's id, and no full name nor phone, as the person keeps his own. A new worker: his phone
    // only if one was typed.
    save.mutate(
      old !== undefined
        ? { ...job, hire_again: old.id }
        : {
            ...job,
            full_name: full,
            ...(typedPhone === "" ? {} : { phone: typedPhone }),
          },
    );
  }

  // Where each refusal shows: beside its box, the form's own first, then the server's. The nickname taken, the whole
  // request's code, beside Jina la kuitwa too, and so not again above the buttons.
  const byField = fieldMessages(save.error);
  const said = (code?: string) =>
    code === undefined ? undefined : codeMessage(codes, code);
  const code =
    save.error instanceof ApiRefusal ? save.error.body.code : undefined;
  const nicknameTaken = code === NICKNAME_TAKEN;
  // The phone found a worker who left: said under Simu, with Mwajiri tena, not above the buttons.
  const phoneOnDemo = code === NO_PHONE_ON_DEMO;
  const askingAboutTheDay =
    askedAbout !== null &&
    askedAbout === firstDay &&
    own.started_on === undefined;

  return (
    // noValidate: the browser's own checks would speak its language, not the shop's.
    <form noValidate onSubmit={send} className="grid gap-6">
      {again === undefined ? (
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
      ) : (
        // On the old job's page, as the status forms are: whom the form hires again.
        <h2 className="text-lg font-semibold">
          {titles("hireAgain", { name: again.display_name })}
        </h2>
      )}
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
        // Mwajiri tena has no Jina kamili: the keyboard starts here, where the button was.
        autoFocus={again !== undefined}
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
      {/* A new worker's phone; a worker hired again keeps his own. */}
      {again === undefined ? (
        <div className="grid gap-2">
          <Field
            label={t("phone")}
            // On the demo, why the box is off, in the server's own sentence, where the hint would be.
            hint={demo ? said(NO_PHONE_ON_DEMO) : t("newPhoneHint")}
            error={phoneOnDemo ? said(NO_PHONE_ON_DEMO) : byField.phone}
            type="tel"
            // A phone's keypad, with + and spaces.
            inputMode="tel"
            value={phone}
            onChange={(event) => {
              setPhone(event.target.value);
              // Another phone is another person, or none: whom the last one found is forgotten.
              setFound(null);
            }}
            disabled={demo}
            autoComplete="off"
            // As typed, longer than the 16 characters stored (StaffAddSerializer, 32).
            maxLength={32}
          />
          {/* Whose phone it is, when it is a worker's who left: a question in words, as the far day's, on the page
              from the start for a screen reader to say when its words come. */}
          <p role="status" className="font-semibold">
            {found
              ? t("foundLeft", {
                  name: found.name,
                  day: formatDay(found.left_on),
                })
              : null}
          </p>
          {found ? (
            <div>
              {/* The second kind: a suggestion beside a box, so the form keeps one main button, Hifadhi, as every
                  form here does. */}
              <Button
                kind="second"
                onClick={() => go(found)}
                disabled={save.isPending || !online}
              >
                {actions("hireAgain")}
              </Button>
            </div>
          ) : null}
        </div>
      ) : null}
      {/* What no box names: an id another shop holds, no network, no key, the server's own problem. Not what is said
          beside a box or under Simu already. */}
      <ApiErrorAlert
        error={
          nicknameTaken || code === LEFT_HERE || phoneOnDemo
            ? null
            : aboutTheWholeRequest(save.error)
        }
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
