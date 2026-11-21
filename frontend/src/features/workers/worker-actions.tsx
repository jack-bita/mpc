// worker-actions.tsx — Badilisha, Simamisha, Rudisha, Ameondoka and Mwajiri tena on a worker's own page (PPL-10, PPL-6,
// PPL-4, PPL-11): the owner fixes a worker's details, stops a worker for a while, brings them back, or records their last
// day, each with a reason, which the audit trail keeps with who and when (rule 7); or hires one who left again.
//
// The worker's status decides which show: working, Badilisha, Simamisha and Ameondoka; suspended, Badilisha, Rudisha
// and Ameondoka; left, Mwajiri tena alone, as leaving is for good and a job that ended keeps what it said then: the
// person comes back with a new job (PPL-11). Once they are back, the old job's page says so, with a link to the new
// one's, in place of the button (Jack: A, the old job stays under Walioondoka). On one's own page there is no button,
// and one line says why, in staff.own's sentence: nobody changes their own job or details (PPL-4, PPL-10).
//
// Mwajiri tena opens Ongeza's own form (worker-form.tsx), its boxes filled from the old job, under the buttons' place;
// saved, the page moves to the new job's page, where the person now works.
//
// Badilisha opens its own form (worker-details-form.tsx) in place of the worker's details: the page hides them while it
// is open (onEditing), as the same details are then in its boxes. The other buttons open their form in place of the
// buttons: Sababu, and for Ameondoka the last day, which starts at the shop's today and offers nothing after it
// (staff.left_in_future) nor before the first day (staff.left_before_start).
// What the form can see is said at once, beside its box, and nothing is sent. The server's own refusals of who may
// (staff.own, staff.more_keys, staff.superuser_only, demo.people_fixed…) show above the buttons; the three that say
// the worker changed since the page read them (staff.not_active, staff.not_suspended, staff.left), as another manager
// got there first, close the form, say it in one line, and read the worker again, so the buttons fit them as they are.
// A suspension sent twice, its first answer lost, ends there too: the second finds Asha already suspended.
//
// No id of the client's: these change a worker, they make nothing, and the status itself refuses a second one.
//
// "use client": it asks use-intl for words (use-client.test.ts), and calls the server.
"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { type FormEvent, useEffect, useRef, useState } from "react";
import { useTranslations } from "use-intl";

import { api } from "@/api/client";
import { useApiErrorWords } from "@/api/errors";
import { aboutTheWholeRequest, answerOf, ApiRefusal } from "@/api/refusal";
import { ApiErrorAlert } from "@/components/api-error-alert";
import { Alert, AlertDescription } from "@/components/design/alert";
import { Button } from "@/components/design/button";
import { Field } from "@/components/design/field";
import { TextLink } from "@/components/design/text-link";
import type { WhoIsHere } from "@/features/people/who-is-here";
import { codeMessage, useCodeWords } from "@/i18n/codes";
import { formatDay } from "@/lib/format";
import { useOnline } from "@/offline/network";
import { shopToday } from "@/offline/rules";

import { DetailsForm } from "./worker-details-form";
import { WorkerForm } from "./worker-form";
import { keepWorker, type Worker, workerPage, WORKERS } from "./workers";

type Action = "edit" | "suspend" | "unsuspend" | "leave" | "hireAgain";
/** The three that change a worker's status, each with its own route. */
type StatusAction = Exclude<Action, "edit" | "hireAgain">;

/** The buttons each status offers, in their order on the page: the fix first, as the mildest. */
const OFFERED: Record<Worker["status"], Action[]> = {
  active: ["edit", "suspend", "leave"],
  suspended: ["edit", "unsuspend", "leave"],
  left: ["hireAgain"],
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

export function WorkerActions({
  worker,
  me,
  demo = false,
  onEditing,
  onForm,
  buttonsHidden = false,
}: {
  worker: Worker;
  me: WhoIsHere;
  /** This is the demo, where no worker gets a phone (worker-details-form.tsx). */
  demo?: boolean;
  /** Badilisha's form opened (true) or closed (false): the page hides the details while it is open. */
  onEditing?: (editing: boolean) => void;
  /** Any of its forms opened (true) or closed (false): the page keeps one form open at a time (worker-page.tsx). */
  onForm?: (open: boolean) => void;
  /** Another card's form is open: its buttons stay off the page meanwhile, so one change is made at a time (PPL-8's
   * review). */
  buttonsHidden?: boolean;
}) {
  const t = useTranslations("workers.actions");
  const codes = useCodeWords();
  const store = useQueryClient();
  const router = useRouter();
  const [open, setOpen] = useState<{ action: Action; today: string } | null>(
    null,
  );
  // The line that says what the last change did, or that someone else changed the worker first.
  const [news, setNews] = useState<string | null>(null);

  // Where the keyboard goes when a form closes. Ghairi: back to the button that opened it. A change: to the line
  // that says what happened, as the button may be gone (Simamisha becomes Rudisha; after Ameondoka, none is left).
  // A new object each time, so each close moves it.
  const buttons = useRef(new Map<Action, HTMLButtonElement>());
  const newsLine = useRef<HTMLDivElement>(null);
  const [backTo, setBackTo] = useState<{ to: Action | "news" } | null>(null);
  useEffect(() => {
    if (backTo === null) return;
    if (backTo.to === "news") newsLine.current?.focus();
    else buttons.current.get(backTo.to)?.focus();
  }, [backTo]);
  // Gone from the page with Badilisha's form open, as at a new read's wait: the page shows the details again.
  useEffect(() => () => onEditing?.(false), [onEditing]);
  // Gone from the page with a form open: the page lets the other card's buttons show again.
  useEffect(() => () => onForm?.(false), [onForm]);

  /** A form opens, or (null) closes: the page learns whether Badilisha's is the one open. */
  function show(form: { action: Action; today: string } | null) {
    setOpen(form);
    onEditing?.(form?.action === "edit");
    onForm?.(form !== null);
  }

  // Nobody changes their own job (PPL-4): no button, and the server's own sentence says why.
  if (worker.id === me.staff.id)
    return <p>{codeMessage(codes, "staff.own")}</p>;

  function said(sentence: string) {
    show(null);
    setNews(sentence);
    setBackTo({ to: "news" });
  }

  function cancelled(action: Action) {
    setBackTo({ to: action });
    show(null);
    // Asked again: a send whose answer was lost may have changed the worker, and the page would go on showing
    // Simamisha for a worker the server suspended (PPL-6's review), as Ongeza's Ghairi asks the list again.
    void store.invalidateQueries({ queryKey: WORKERS });
  }

  return (
    <div className="grid gap-4">
      {/* Always on the page, empty and hidden until something happens: a role="status" box is read when its words
          change, and one that appears with its words already in it may not be read at all (offline-banner.tsx). */}
      <div
        ref={newsLine}
        tabIndex={-1}
        className={news ? "outline-none" : "sr-only"}
      >
        <Alert kind="info">
          {news ? <AlertDescription>{news}</AlertDescription> : null}
        </Alert>
      </div>
      {open?.action === "edit" ? (
        <DetailsForm
          worker={worker}
          today={open.today}
          demo={demo}
          // The worker as the server answered: their nickname as it is now.
          onDone={(changed) =>
            said(t("done.edit", { name: changed.display_name }))
          }
          onNothingChanged={() => said(t("nothingChanged"))}
          onChangedMeanwhile={said}
          onCancel={() => cancelled("edit")}
        />
      ) : open?.action === "hireAgain" ? (
        <WorkerForm
          today={open.today}
          again={worker}
          // He works on his new job now: its page. Its back arrow returns here when this page was reached inside the
          // app, else to the list (in-app-moves.tsx), as for any page.
          onSaved={(back) => router.push(workerPage(back.id))}
          onCancel={() => cancelled("hireAgain")}
        />
      ) : open !== null ? (
        <ActionForm
          action={open.action}
          worker={worker}
          today={open.today}
          onDone={(action, changed) =>
            // The worker as the server answered: a last day only once they left.
            said(
              t(`done.${action}`, {
                name: changed.display_name,
                day: changed.left_on === null ? "" : formatDay(changed.left_on),
              }),
            )
          }
          onChangedMeanwhile={said}
          onCancel={() => cancelled(open.action)}
        />
      ) : worker.hired_again_as !== null ? (
        // Back already: the old job links to the new one in place of Mwajiri tena.
        <p>
          {t("back", { name: worker.display_name })}{" "}
          <TextLink href={workerPage(worker.hired_again_as)}>
            {t("backLink")}
          </TextLink>
        </p>
      ) : !buttonsHidden && OFFERED[worker.status].length > 0 ? (
        <div className="flex flex-wrap gap-3">
          {OFFERED[worker.status].map((action) => (
            <Button
              // Each in its place: after a suspension, Rudisha takes Simamisha's place, and Ameondoka keeps its own.
              key={action}
              ref={(button) => {
                if (button) buttons.current.set(action, button);
                else buttons.current.delete(action);
              }}
              // Leaving is for good: the danger kind, as the device's Zuia.
              kind={action === "leave" ? "danger" : "second"}
              onClick={() => {
                setNews(null);
                // The shop's today, read as the form opens: a page left open overnight starts on the new day.
                show({
                  action,
                  today: shopToday(me.shop.timezone, Date.now()),
                });
              }}
            >
              {t(action)}
            </Button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function ActionForm({
  action,
  worker,
  today,
  onDone,
  onChangedMeanwhile,
  onCancel,
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
  onCancel: () => void;
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

  function send(event: FormEvent) {
    // The browser would send the form itself and load a new page; the app sends it instead.
    event.preventDefault();
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
  // BESIDE_A_BOX). Everything else is ApiErrorAlert's, above the buttons; the codes of a change meanwhile close the
  // form instead.
  const byField = fieldMessages(change.error);
  const sayCode = (code?: string) =>
    code === undefined ? undefined : codeMessage(codes, code);
  const code =
    change.error instanceof ApiRefusal ? change.error.body.code : undefined;
  const besideBox = code === undefined ? undefined : BESIDE_A_BOX[code];
  const above =
    besideBox !== undefined ? null : aboutTheWholeRequest(change.error);

  return (
    // noValidate: the browser's own checks would speak its language, not the shop's.
    <form noValidate onSubmit={send} className="grid gap-6">
      <h2 className="text-lg font-semibold">
        {t(`title.${action}`, { name: worker.display_name })}
      </h2>
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
        // The person just asked for this form: the keyboard starts in its first box, where the button was.
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
      <div className="flex flex-wrap gap-3">
        {/* Switched off while it is sent, so a second tap sends nothing, and while offline, so nothing waits unsent
            while it looks done (setting-form.tsx). */}
        <Button
          type="submit"
          kind={action === "leave" ? "danger" : "main"}
          disabled={change.isPending || !online}
        >
          {t("save")}
        </Button>
        <Button kind="second" onClick={onCancel}>
          {t("cancel")}
        </Button>
      </div>
    </form>
  );
}
