// worker-actions.tsx — Taarifa zake, a worker's details with Badilisha, Simamisha, Rudisha, Ameondoka and Mwajiri
// tena, on their own page (PPL-10, PPL-6, PPL-4, PPL-11, UI-10): the owner fixes a worker's details, stops a worker for
// a while, brings them back, or records their last day, each with a reason, which the audit trail keeps with who and
// when (rule 7); or hires one who left again.
//
// The worker's status decides which show: working, Badilisha, Simamisha and Ameondoka; suspended, Badilisha, Rudisha
// and Ameondoka; left, Mwajiri tena alone, as leaving is for good and a job that ended keeps what it said then: the
// person comes back with a new job (PPL-11). Once they are back, the old job's page says so, with a link to the new
// one's, in place of the button (Jack: A, the old job stays under Walioondoka). On one's own page there is no button,
// and one line says why, in staff.own's sentence: nobody changes their own job or details (PPL-4, PPL-10).
//
// All of it is one card, Taarifa zake (UI-10, as Jack pictured the page on 20 Nov 2026): its heading, with Badilisha on
// the heading's row (card-heading.tsx), as it changes the whole card; the worker's details, which the page hands in
// (`details`); and under them the buttons of the worker's status, as they act on the person the details describe.
//
// Badilisha is a link to its own page, Badilisha taarifa za Juma (edit-worker-screen.tsx, UI-11), as a long form keeps
// a page of its own; once done, that page comes back here and leaves its line on this card (`arrived`, page-news.ts).
//
// Mwajiri tena is a link to its own page too, Mwajiri tena Baraka (new-worker-screen.tsx, UI-11): Ongeza's own form, its
// boxes filled from the old job; saved, it lands on the new job's page, where the person now works.
//
// Simamisha, Rudisha and Ameondoka are short: each opens a sheet over the page (UI-10, sheet.tsx), titled with what and
// who, "Simamisha Asha", with Sababu, and for Ameondoka the last day, which starts at the shop's today and offers
// nothing after it (staff.left_in_future) nor before the first day (staff.left_before_start). Its main button names the
// action, Simamisha, Mrudishe or Ameondoka, red for Ameondoka, as leaving is for good (Jack: yes, UI-10). The buttons
// stay on the page under the sheet. As it closes, the sheet alone moves the keyboard (its finalFocus): after a change,
// to the done line, as the button is gone (Simamisha becomes Rudisha); after Ghairi, back to the very button that
// opened it. Base UI moves it a moment after the sheet goes, so a second mover of ours would race it (UI-10's review).
// What the sheet can see is said at once, beside its box, and nothing is sent. The server's own refusals of who may
// (staff.own, staff.more_keys, staff.superuser_only, demo.people_fixed…) show inside the sheet, above its buttons; the
// three that say the worker changed since the page read them (staff.not_active, staff.not_suspended, staff.left), as
// another manager got there first, close the sheet, say it in one line on the card, and read the worker again, so the
// buttons fit them as they are. A suspension sent twice, its first answer lost, ends there too: the second finds Asha
// already suspended.
//
// No id of the client's: these change a worker, they make nothing, and the status itself refuses a second one.
//
// "use client": it asks use-intl for words (use-client.test.ts), and calls the server.
"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { type ReactNode, useEffect, useId, useRef, useState } from "react";
import { useTranslations } from "use-intl";

import { api } from "@/api/client";
import { useApiErrorWords } from "@/api/errors";
import { aboutTheWholeRequest, answerOf, ApiRefusal } from "@/api/refusal";
import { ApiErrorAlert } from "@/components/api-error-alert";
import { Alert, AlertDescription } from "@/components/design/alert";
import { Button, ButtonLink } from "@/components/design/button";
import { Card, CardContent } from "@/components/design/card";
import { Field } from "@/components/design/field";
import { Sheet } from "@/components/design/sheet";
import { TextLink } from "@/components/design/text-link";
import type { WhoIsHere } from "@/features/people/who-is-here";
import { codeMessage, useCodeWords } from "@/i18n/codes";
import { formatDay } from "@/lib/format";
import { useOnline } from "@/offline/network";
import { shopToday } from "@/offline/rules";

import { CardHeading } from "./card-heading";
import {
  editWorkerPage,
  hireAgainPage,
  keepWorker,
  type Worker,
  workerPage,
  WORKERS,
} from "./workers";

/** The three that change a worker's status, each with its own route, and each in a sheet (UI-10). */
type StatusAction = "suspend" | "unsuspend" | "leave";

/** The status buttons under the details, in their order on the page, for a worker working or suspended. Badilisha
 * isn't among them: it sits on the heading's row (UI-10); nor Mwajiri tena, a link to its own page, for one who left
 * (UI-11). */
const OFFERED: Record<"active" | "suspended", StatusAction[]> = {
  active: ["suspend", "leave"],
  suspended: ["unsuspend", "leave"],
};

/** The whole request's codes that are about one box: shown beside it, not above the buttons. The services raise them
 * with no field (apps/core/api/errors.py), as they check the reason and the day after the form's own checks. */
const BESIDE_A_BOX: Record<string, "reason" | "left_on"> = {
  "staff.reason_required": "reason",
  "staff.left_in_future": "left_on",
  "staff.left_before_start": "left_on",
};

/** The codes that say the worker changed since the page read them. */
const CHANGED_MEANWHILE = new Set([
  "staff.not_active",
  "staff.not_suspended",
  "staff.left",
]);

/** The form's own checks, by box, as the codes the server would send. */
type Checks = { reason?: string; left_on?: string };

/** The shop's today, read at the tap that opens a sheet. Out here, as React's check of what a draw may call can't tell
 * that a button's handler is only ever called by a tap, never while the page draws. */
function todayAt(zone: string): string {
  return shopToday(zone, Date.now());
}

export function WorkerActions({
  worker,
  me,
  details,
  arrived = null,
  buttonsHidden = false,
}: {
  worker: Worker;
  me: WhoIsHere;
  /** The worker's details, as the page draws them: under the card's heading. */
  details?: ReactNode;
  /** The line a form's own page left as it landed here, "Juma ameongezwa…" (UI-11, page-news.ts). */
  arrived?: string | null;
  /** Another card's form is open: its buttons stay off the page meanwhile, so one change is made at a time (PPL-8's
   * review). */
  buttonsHidden?: boolean;
}) {
  const t = useTranslations("workers.actions");
  const view = useTranslations("workers.view");
  const codes = useCodeWords();
  const store = useQueryClient();
  const titleId = useId();
  // The sheet open, if any, with the shop's today as it opened.
  const [open, setOpen] = useState<{
    action: StatusAction;
    today: string;
  } | null>(null);
  // The line that says what the last change did, or that someone else changed the worker first. From its first draw,
  // the line a form's own page left, if it left one (UI-11).
  const [news, setNews] = useState<string | null>(arrived);

  // The status buttons, for a sheet to give the keyboard back to the very one that opened it (its finalFocus below),
  // and the done line, for it to go to after a change.
  const buttons = useRef(new Map<StatusAction, HTMLButtonElement>());
  const newsLine = useRef<HTMLDivElement>(null);
  // The line a form's own page left (UI-11) is on the card from its first draw, and the keyboard goes to it, as after a
  // change made here: a screen reader says what it is put on, as a status box that comes with its words in it may go
  // unsaid (offline-banner.tsx).
  useEffect(() => {
    if (arrived) newsLine.current?.focus();
  }, [arrived]);

  // Nobody changes their own job (PPL-4): no button, and the server's own sentence says why, under the details.
  const own = worker.id === me.staff.id;

  // Whether the last close was a change, for the sheet to give the keyboard to the done line: read as the sheet goes,
  // which is after the draw that took it away, so a ref, not the state.
  const afterChange = useRef(false);

  function said(sentence: string) {
    afterChange.current = true;
    setOpen(null);
    setNews(sentence);
  }

  function cancelled() {
    setOpen(null);
    // Asked again: a send whose answer was lost may have changed the worker, and the page would go on showing
    // Simamisha for a worker the server suspended (PPL-6's review).
    void store.invalidateQueries({ queryKey: WORKERS });
  }

  /** A button opens its sheet. The shop's today is read as it opens: a page left open overnight starts on the new
   * day. */
  function openSheet(action: StatusAction) {
    afterChange.current = false;
    setNews(null);
    setOpen({ action, today: todayAt(me.shop.timezone) });
  }

  // Badilisha, on the heading's row: for a worker working or suspended, as one who left keeps what they were then
  // (PPL-11); while no form is open in the page, on another card.
  const editOffered = !own && worker.status !== "left" && !buttonsHidden;

  return (
    <Card>
      <CardContent>
        {/* One region for the whole card, so a screen reader names each button by the card it belongs to. */}
        <section aria-labelledby={titleId} className="grid gap-4">
          <CardHeading id={titleId} title={view("details")}>
            {editOffered ? (
              // A link, as it opens a page of its own (UI-11). Normal, on the heading's row, which a big one would
              // crowd.
              <ButtonLink
                href={editWorkerPage(worker.id)}
                kind="second"
                size="normal"
              >
                {t("edit")}
              </ButtonLink>
            ) : null}
          </CardHeading>
          {details}
          {own ? (
            <p>{codeMessage(codes, "staff.own")}</p>
          ) : (
            <>
              {/* Always on the page, empty and hidden until something happens: a role="status" box is read when its
                  words change, and one that appears with its words already in it may not be read at all
                  (offline-banner.tsx). */}
              <div
                ref={newsLine}
                tabIndex={-1}
                className={news ? "outline-none" : "sr-only"}
              >
                <Alert kind="info">
                  {news ? <AlertDescription>{news}</AlertDescription> : null}
                </Alert>
              </div>
              {worker.hired_again_as !== null ? (
                // Back already: the old job links to the new one in place of Mwajiri tena.
                <p>
                  {t("back", { name: worker.display_name })}{" "}
                  <TextLink href={workerPage(worker.hired_again_as)}>
                    {t("backLink")}
                  </TextLink>
                </p>
              ) : worker.status === "left" ? (
                // A link, as it opens a page of its own (UI-11), where he comes back with a new job (PPL-11).
                <div>
                  <ButtonLink href={hireAgainPage(worker.id)} kind="second">
                    {t("hireAgain")}
                  </ButtonLink>
                </div>
              ) : !buttonsHidden ? (
                <div className="flex flex-wrap gap-3">
                  {OFFERED[worker.status].map((action) => (
                    <Button
                      // Each in its place: after a suspension, Rudisha takes Simamisha's place, and Ameondoka keeps
                      // its own.
                      key={action}
                      ref={(element) => {
                        if (element) buttons.current.set(action, element);
                        else buttons.current.delete(action);
                      }}
                      // Leaving is for good: the danger kind, as the device's Zuia.
                      kind={action === "leave" ? "danger" : "second"}
                      onClick={() => openSheet(action)}
                    >
                      {t(action)}
                    </Button>
                  ))}
                </div>
              ) : null}
              {/* Mounted only while open, so a sheet closed with Ghairi forgets what was typed (as the day's,
                  ATT-6). */}
              {open !== null ? (
                <ActionSheet
                  action={open.action}
                  worker={worker}
                  today={open.today}
                  onDone={(action, changed) =>
                    // The worker as the server answered: a last day only once they left.
                    said(
                      t(`done.${action}`, {
                        name: changed.display_name,
                        day:
                          changed.left_on === null
                            ? ""
                            : formatDay(changed.left_on),
                      }),
                    )
                  }
                  onChangedMeanwhile={said}
                  onCancel={cancelled}
                  // After a change, the done line; after Ghairi, the very button that opened it, named, never left to
                  // Base UI's guess, which on a phone's tap may be an element of an earlier opening (UI-10's review).
                  finalFocus={() =>
                    afterChange.current
                      ? newsLine.current
                      : (buttons.current.get(open.action) ?? null)
                  }
                />
              ) : null}
            </>
          )}
        </section>
      </CardContent>
    </Card>
  );
}

/** Simamisha, Rudisha or Ameondoka, in a sheet over the worker's page (UI-10). */
function ActionSheet({
  action,
  worker,
  today,
  onDone,
  onChangedMeanwhile,
  onCancel,
  finalFocus,
}: {
  action: StatusAction;
  worker: Worker;
  /** The shop's today: where the last day starts, and the latest it may be. */
  today: string;
  /** Done: which of the three, as a callback can't see the page's narrowing of its own `open.action`, and the worker
   * as the server answered. */
  onDone: (action: StatusAction, worker: Worker) => void;
  /** Someone else changed the worker first: what the server's code says. */
  onChangedMeanwhile: (sentence: string) => void;
  /** Ghairi or Esc. */
  onCancel: () => void;
  /** Where the keyboard goes as the sheet goes (sheet.tsx). */
  finalFocus: () => HTMLElement | null;
}) {
  const t = useTranslations("workers.actions");
  const codes = useCodeWords();
  const { fieldMessages } = useApiErrorWords();
  const online = useOnline();
  const store = useQueryClient();
  const [reason, setReason] = useState("");
  const [lastDay, setLastDay] = useState(today);
  const [own, setOwn] = useState<Checks>({});

  const change = useMutation({
    mutationFn: ({ reason, left_on }: { reason: string; left_on: string }) => {
      const path = { path: { id: worker.id } };
      if (action === "suspend")
        return answerOf(
          api.POST("/api/v1/people/staff/{id}/suspend/", {
            params: path,
            body: { reason },
          }),
        );
      if (action === "unsuspend")
        return answerOf(
          api.POST("/api/v1/people/staff/{id}/unsuspend/", {
            params: path,
            body: { reason },
          }),
        );
      return answerOf(
        api.POST("/api/v1/people/staff/{id}/leave/", {
          params: path,
          body: { reason, left_on },
        }),
      );
    },
    onSuccess: (changed) => {
      // The worker as they are now, on their page and in the list at once, then both asked again (workers.ts).
      keepWorker(store, changed);
      void store.invalidateQueries({ queryKey: WORKERS });
      onDone(action, changed);
    },
    onError: (error) => {
      // Someone else got there first: read the worker again, so the buttons fit them as they are now.
      if (
        error instanceof ApiRefusal &&
        CHANGED_MEANWHILE.has(error.body.code)
      ) {
        void store.invalidateQueries({ queryKey: WORKERS });
        onChangedMeanwhile(codeMessage(codes, error.body.code));
      }
    },
  });

  /** The sheet's main button, or Enter in a box: the sheet's own form stops the browser's send (sheet.tsx). */
  function send() {
    // The last send's refusal is about what was sent then: each tap shows only what it finds (setting-form.tsx).
    change.reset();
    // Spaces alone are no reason, as the server says too.
    const why = reason.trim();
    const checks: Checks = {};
    if (why === "") checks.reason = "staff.reason_required";
    if (action === "leave") {
      // Days as text sort as days do: "2026-11-18" < "2026-11-19".
      if (lastDay === "") checks.left_on = "required";
      else if (lastDay > today) checks.left_on = "staff.left_in_future";
      else if (lastDay < worker.started_on)
        checks.left_on = "staff.left_before_start";
    }
    setOwn(checks);
    if (Object.keys(checks).length > 0) return;
    change.mutate({ reason: why, left_on: lastDay });
  }

  // Where each refusal shows: beside its box, the form's own first, then the server's, by field or by its code (see
  // BESIDE_A_BOX). Everything else is ApiErrorAlert's, above the sheet's buttons; the codes of a change meanwhile close
  // the sheet instead.
  const byField = fieldMessages(change.error);
  const sayCode = (code?: string) =>
    code === undefined ? undefined : codeMessage(codes, code);
  const code =
    change.error instanceof ApiRefusal ? change.error.body.code : undefined;
  const besideBox = code === undefined ? undefined : BESIDE_A_BOX[code];
  const above =
    besideBox !== undefined ? null : aboutTheWholeRequest(change.error);

  return (
    <Sheet
      open
      onClose={onCancel}
      title={t(`title.${action}`, { name: worker.display_name })}
      // Names the action, as the last tap should say what it does (UI-10); red for Ameondoka, as leaving is for good.
      actionLabel={t(`confirm.${action}`)}
      actionKind={action === "leave" ? "danger" : "main"}
      onAction={send}
      // Held while it is sent, so a second tap sends nothing, and the sheet stays until its answer comes.
      busy={change.isPending}
      // Offline, nothing is sent, so nothing waits unsent while it looks done (setting-form.tsx).
      actionDisabled={!online}
      finalFocus={finalFocus}
    >
      <Field
        label={t("reason")}
        hint={t("reasonHint")}
        error={
          sayCode(own.reason) ??
          (besideBox === "reason" ? sayCode(code) : undefined) ??
          byField.reason
        }
        value={reason}
        onChange={(event) => setReason(event.target.value)}
        autoComplete="off"
        // As the audit line keeps it (StaffReasonSerializer, 500 characters).
        maxLength={500}
        // The person just asked for this sheet: the keyboard starts in its first box.
        autoFocus
      />
      {action === "leave" ? (
        <Field
          label={t("lastDay")}
          hint={t("lastDayHint")}
          error={
            sayCode(own.left_on) ??
            (besideBox === "left_on" ? sayCode(code) : undefined) ??
            byField.left_on
          }
          type="date"
          // The phone's calendar offers nothing after today nor before the first day.
          max={today}
          min={worker.started_on}
          value={lastDay}
          onChange={(event) => setLastDay(event.target.value)}
        />
      ) : null}
      {/* Who may (staff.own, staff.more_keys, staff.superuser_only, demo.people_fixed), no network, the server's own
          problem. */}
      <ApiErrorAlert error={above} />
    </Sheet>
  );
}
