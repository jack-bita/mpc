// worker-details-form.tsx — Badilisha (PPL-10): the owner fixes a worker's details, typed wrong when they were added,
// or changed since: the same details as the worker's page shows them, now in boxes, already filled in, with Sababu and
// Hifadhi (Jack, 18 Nov 2026). On a page of its own since UI-11, Badilisha taarifa za Juma (edit-worker-screen.tsx),
// which gives the title and the way back, its arrow: no Ghairi (Jack's yes to the screens, 21 Nov 2026).
//
// Five boxes: Jina kamili and Simu, which are the person's own and follow them to every shop where they work; Jina la
// kuitwa, Kazi and Siku ya kwanza, which are their job's here. The phone shows as the shop writes it, "0712 345 678",
// and the server cleans whatever is typed into its one stored form; an empty box takes the phone off. Sababu is asked
// every time (Jack, PPL-10: A): the audit trail keeps each fix with who, when and why, as the full name and the phone
// have no other history.
//
// Only the boxes that changed are sent, with the version of the worker the form opened on (apps/core/editing.py). If
// someone else fixed them since, the server refuses it (409 version_conflict): the form is done, one line on the
// worker's page says they changed since the form opened, and the page reads them again, so nobody's fix is undone by an
// old copy. The version and each box's start are kept from the moment the form opened, never the page's newer read:
// sending a newer version with boxes typed on an older copy would undo the other person's fix all the same.
//
// What the form can see is said at once, beside its box, in the server's own sentences, and nothing is sent: an empty
// name or nickname (`blank`), an empty first day (`required`), an empty Sababu (staff.reason_required). A first day
// moved more than 30 days from both today and the day it was is asked about once, as a year typed wrong would be on
// Ongeza (worker-form.tsx); fixing a long-time worker's first day by a few days asks nothing (PPL-10's review). The
// server says the rest: a wrong phone (phone.invalid) and one another person has (`unique`) beside Simu, a nickname
// another current worker has (staff.display_name_taken) beside Jina la kuitwa, and who may (staff.own,
// staff.more_keys…) above the buttons.
//
// On the demo, the phone box is off and says why (demo.phones_fixed, Jack, PPL-10: A): every visitor logs in as
// Meneja, so a stranger's real number would show to every later visitor. The page learns the demo's sign and hands it
// down (worker-page.tsx); the server refuses a phone there too.
//
// No id of the client's: a fix makes nothing, and the version refuses a second one sent on the same copy.
//
// "use client": it asks use-intl for words (use-client.test.ts), and calls the server.
"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { useTranslations } from "use-intl";

import { api } from "@/api/client";
import { useApiErrorWords } from "@/api/errors";
import { aboutTheWholeRequest, answerOf, ApiRefusal } from "@/api/refusal";
import type { components } from "@/api/schema";
import { ApiErrorAlert } from "@/components/api-error-alert";
import { Button } from "@/components/design/button";
import { Field } from "@/components/design/field";
import { PAY } from "@/features/pay/pay";
import { codeMessage, useCodeWords } from "@/i18n/codes";
import { formatDay, formatPhone } from "@/lib/format";
import { useOnline } from "@/offline/network";

import { keepWorker, type Worker, WORKERS } from "./workers";

type Fix = components["schemas"]["StaffEditRequest"];

/** The boxes, in their order on the page. */
const BOXES = [
  "full_name",
  "display_name",
  "job_title",
  "started_on",
  "phone",
] as const;
type Box = (typeof BOXES)[number];

/** How far a first day may move, from today and from the day it was, before the form asks once more: about a month,
 * either way, as on Ongeza. */
const FAR_DAYS = 30;

/** The whole request's codes that are about one box: shown beside it, not above the buttons. The services raise them
 * with no field (apps/core/api/errors.py). */
const BESIDE_A_BOX: Record<string, Box | "reason"> = {
  "staff.display_name_taken": "display_name",
  "staff.reason_required": "reason",
  "demo.phones_fixed": "phone",
};

/** The codes that say the worker changed since the form opened: an older copy, or a worker who left meanwhile. */
const CHANGED_MEANWHILE = new Set(["version_conflict", "staff.left"]);

/** The form's own checks, by box, as the codes the server would send. */
type Checks = Partial<Record<Box | "reason", string>>;

/** The days from one day to another, as on Ongeza: both read at midnight UTC, so no clock change moves the count. */
function daysBetween(from: string, to: string): number {
  return (Date.parse(to) - Date.parse(from)) / 86_400_000;
}

/** What each box starts at: the worker as the page shows them, the phone as the shop writes it. */
function boxesOf(worker: Worker): Record<Box, string> {
  return {
    full_name: worker.full_name,
    display_name: worker.display_name,
    job_title: worker.job_title,
    started_on: worker.started_on,
    phone: worker.phone === null ? "" : formatPhone(worker.phone),
  };
}

export function DetailsForm({
  worker,
  today,
  demo,
  onDone,
  onNothingChanged,
  onChangedMeanwhile,
}: {
  worker: Worker;
  /** The shop's today: what a far first day is measured from. */
  today: string;
  /** This is the demo, where no worker gets a phone. */
  demo: boolean;
  onDone: (worker: Worker) => void;
  /** Hifadhi with every box as it started. */
  onNothingChanged: () => void;
  /** Someone else changed the worker first: what to say. */
  onChangedMeanwhile: (sentence: string) => void;
}) {
  const t = useTranslations("workers");
  const codes = useCodeWords();
  const { fieldMessages } = useApiErrorWords();
  const online = useOnline();
  const store = useQueryClient();

  // The worker as the form opened on them, kept: what "changed" means, and the version sent back (see the top).
  const [start] = useState(() => ({
    boxes: boxesOf(worker),
    version: worker.version,
  }));
  const [boxes, setBoxes] = useState(start.boxes);
  const [reason, setReason] = useState("");
  const [own, setOwn] = useState<Checks>({});
  // The far first day the form has asked about: Hifadhi again with this same day sends it.
  const [askedAbout, setAskedAbout] = useState<string | null>(null);

  const fix = useMutation({
    mutationFn: (body: Fix) =>
      answerOf(
        api.PATCH("/api/v1/people/staff/{id}/", {
          params: { path: { id: worker.id } },
          body,
        }),
      ),
    onSuccess: (changed) => {
      // The worker as they are now, on their page and in the list at once, then both asked again (workers.ts).
      keepWorker(store, changed);
      void store.invalidateQueries({ queryKey: WORKERS });
      // A first day moved moves the days they are paid for, and a nickname is the pay's line (WAGE-2).
      void store.invalidateQueries({ queryKey: PAY });
      onDone(changed);
    },
    onError: (error) => {
      // The worker changed since the form opened: someone else got there first, or this very fix went through and its
      // answer was lost, then was sent again. Read the worker again, so the page shows them as they are now; the line
      // says what happened in words true of both (PPL-10's review).
      if (
        error instanceof ApiRefusal &&
        CHANGED_MEANWHILE.has(error.body.code)
      ) {
        void store.invalidateQueries({ queryKey: WORKERS });
        onChangedMeanwhile(
          error.body.code === "version_conflict"
            ? t("actions.changedMeanwhile", { name: worker.display_name })
            : codeMessage(codes, error.body.code),
        );
      }
    },
  });

  function setBox(box: Box, value: string) {
    setBoxes((typed) => ({ ...typed, [box]: value }));
  }

  function send(event: FormEvent) {
    // The browser would send the form itself and load a new page; the app sends it instead.
    event.preventDefault();
    // The last send's refusal is about what was sent then: each tap shows only what it finds (setting-form.tsx).
    fix.reset();
    // As the server keeps them: the spaces around each taken off, so spaces alone are no name.
    const now = Object.fromEntries(
      BOXES.map((box) => [box, boxes[box].trim()]),
    ) as Record<Box, string>;
    const changed = BOXES.filter((box) => now[box] !== start.boxes[box]);
    if (changed.length === 0) {
      onNothingChanged();
      return;
    }
    const why = reason.trim();
    const checks: Checks = {};
    if (now.full_name === "") checks.full_name = "blank";
    if (now.display_name === "") checks.display_name = "blank";
    if (now.started_on === "") checks.started_on = "required";
    if (why === "") checks.reason = "staff.reason_required";
    setOwn(checks);
    if (Object.keys(checks).length > 0) return;
    // A first day moved far from both today and the day it was: asked about once, beside its box; the same day again
    // is the owner's answer. Far from today alone is no sign of a slip: a worker who started two years ago is.
    const far =
      changed.includes("started_on") &&
      Math.abs(daysBetween(today, now.started_on)) > FAR_DAYS &&
      Math.abs(daysBetween(start.boxes.started_on, now.started_on)) > FAR_DAYS;
    if (far && askedAbout !== now.started_on) {
      setAskedAbout(now.started_on);
      return;
    }
    fix.mutate({
      version: start.version,
      reason: why,
      ...Object.fromEntries(changed.map((box) => [box, now[box]])),
    });
  }

  // Where each refusal shows: beside its box, the form's own first, then the server's, by field or by its code (see
  // BESIDE_A_BOX). Everything else is ApiErrorAlert's, above the buttons; a change meanwhile ends the form, its line on
  // the worker's page.
  const byField = fieldMessages(fix.error);
  const said = (code?: string) =>
    code === undefined ? undefined : codeMessage(codes, code);
  const code =
    fix.error instanceof ApiRefusal ? fix.error.body.code : undefined;
  const besideBox = code === undefined ? undefined : BESIDE_A_BOX[code];
  const errorOf = (box: Box | "reason") =>
    said(own[box]) ?? (besideBox === box ? said(code) : undefined);
  const above =
    besideBox !== undefined || (code && CHANGED_MEANWHILE.has(code))
      ? null
      : aboutTheWholeRequest(fix.error);
  const askingAboutTheDay =
    askedAbout !== null &&
    askedAbout === boxes.started_on.trim() &&
    own.started_on === undefined;

  return (
    // noValidate: the browser's own checks would speak its language, not the shop's.
    <form noValidate onSubmit={send} className="grid gap-6">
      <Field
        label={t("form.fullName")}
        hint={t("form.fullNameHint")}
        error={errorOf("full_name") ?? byField.full_name}
        value={boxes.full_name}
        onChange={(event) => setBox("full_name", event.target.value)}
        autoComplete="off"
        // As the server keeps it (User.full_name, 150 characters).
        maxLength={150}
        // The person just asked for this form: the keyboard starts in its first box, where Badilisha was.
        autoFocus
      />
      <Field
        label={t("form.nickname")}
        hint={t("form.nicknameHint")}
        error={errorOf("display_name") ?? byField.display_name}
        value={boxes.display_name}
        onChange={(event) => setBox("display_name", event.target.value)}
        autoComplete="off"
        // As the server keeps it (StaffMember.display_name, 40 characters).
        maxLength={40}
      />
      <Field
        label={t("form.jobTitle")}
        hint={t("form.jobTitleHint")}
        error={byField.job_title}
        value={boxes.job_title}
        onChange={(event) => setBox("job_title", event.target.value)}
        autoComplete="off"
        // As the server keeps it (StaffMember.job_title, 60 characters).
        maxLength={60}
      />
      <div className="grid gap-2">
        <Field
          label={t("form.firstDay")}
          hint={t("form.firstDayHint")}
          error={errorOf("started_on") ?? byField.started_on}
          type="date"
          value={boxes.started_on}
          onChange={(event) => setBox("started_on", event.target.value)}
        />
        {/* The question about a far day, under its box: in words, not in red, as it is a question, not a refusal.
            On the page from the start, empty, so a screen reader reads it when its words come (worker-form.tsx). */}
        <p role="status" className="font-semibold">
          {askingAboutTheDay
            ? t("form.farDay", { day: formatDay(boxes.started_on.trim()) })
            : null}
        </p>
      </div>
      <Field
        label={t("form.phone")}
        // On the demo, why the box is off, in the server's own sentence, where the hint would be.
        hint={
          demo ? codeMessage(codes, "demo.phones_fixed") : t("form.phoneHint")
        }
        error={errorOf("phone") ?? byField.phone}
        type="tel"
        // A phone's keypad, with + and spaces.
        inputMode="tel"
        value={boxes.phone}
        onChange={(event) => setBox("phone", event.target.value)}
        disabled={demo}
        autoComplete="off"
        // As typed, longer than the 16 characters stored (StaffEditSerializer, 32).
        maxLength={32}
      />
      <Field
        label={t("actions.reason")}
        hint={t("actions.reasonHint")}
        error={errorOf("reason") ?? byField.reason}
        value={reason}
        onChange={(event) => setReason(event.target.value)}
        autoComplete="off"
        // As the audit line keeps it (StaffReasonSerializer, 500 characters).
        maxLength={500}
      />
      {/* Who may (staff.own, staff.more_keys, staff.superuser_only, demo.people_fixed), no network, the server's own
          problem. */}
      <ApiErrorAlert error={above} />
      <div className="flex flex-wrap gap-3">
        {/* Switched off while it is sent, so a second tap sends nothing, and while offline, so nothing waits unsent
            while it looks done (setting-form.tsx). */}
        <Button type="submit" disabled={fix.isPending || !online}>
          {t("actions.save")}
        </Button>
      </div>
    </form>
  );
}
