// closure-last-day.tsx — Badilisha siku ya mwisho: move a closure's last day, earlier or later, with a reason (ATT-9,
// ATT-8's change_last_day). Opens under the closure's line on Siku duka limefungwa, for someone holding settings.manage
// on the whole shop. The shop closes 20–24 November for a funeral; the family finishes on the 22nd, so the owner moves
// the last day to the 22nd and the shop opens on the 23rd; or the funeral runs longer, and the last day moves later.
//
// It works on a closure already begun too, where Ondoa no longer can: the days that change are the ones between the
// old last day and the new, and none of them may be before today, as a past day may already be worked out and paid
// (ATT-10). Moved earlier, the new last day may be yesterday at the earliest, which opens the shop from today; moved
// later, every new day is after the old last day, which is today or later, as the list holds no closure already over.
// So the box offers nothing before the later of the closure's first day and yesterday, and starts at its last day now.
// A last day moved to yesterday ends the closure: it leaves the list, and the section says so.
//
// What the form can see itself is said at once, in the server's own sentences, and nothing is sent: an empty box, a
// last day before the first (closure.ends_before_it_starts), one that would open a past day again (closure.date_past),
// an empty reason. The server checks the rest: days another closure has (closure.overlaps), said above the buttons, as
// it is about the days together, as the list is read again, so the closure it clashes with shows, one added meanwhile
// among them (ATT-9's review); on the demo, a person's change of today (demo.closures_from_tomorrow), beside the box;
// and a closure someone else cancelled meanwhile (closure.not_active), which the section says, reading the list again,
// as the closure has left it.
//
// It carries no id: a move sent again finds the same last day, which the server writes nothing for, and answers the
// closure as it is. So the form sends nothing when the box still holds the last day the closure has: the server would
// change nothing and keep no reason, and the page would say the last day changed (ATT-9's review). It says so beside
// the box instead, in the page's own sentence, as no server code says it.
//
// "use client": it asks use-intl for words (use-client.test.ts), and calls the server.
"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CircleAlert } from "lucide-react";
import { type FormEvent, useState } from "react";
import { useTranslations } from "use-intl";

import { api } from "@/api/client";
import { useApiErrorWords } from "@/api/errors";
import { aboutTheWholeRequest, answerOf, ApiRefusal } from "@/api/refusal";
import { ApiErrorAlert } from "@/components/api-error-alert";
import { Alert, AlertDescription, AlertTitle } from "@/components/design/alert";
import { Button } from "@/components/design/button";
import { Field } from "@/components/design/field";
import { codeMessage, useCodeWords } from "@/i18n/codes";
import { dayBefore, formatDay } from "@/lib/format";
import { useOnline } from "@/offline/network";

import { type Closure, CLOSURES, dropClosure, keepClosure } from "./closures";

// The fields with a box, beside which their refusals show. A refusal of any other field shows above the buttons.
const ON_A_BOX = new Set(["last_day", "reason"]);

/** The form's own checks, by box, as the codes the server would send, or SAME_DAY, which no server code says. */
type Checks = { last_day?: string; reason?: string };

/** The form's own mark for a box still holding the last day the closure has (see the top of this file). */
const SAME_DAY = "same_day";

export function ClosureLastDay({
  closure,
  today,
  onMoved,
  onGone,
  onCancel,
}: {
  closure: Closure;
  /** The shop's today, from the server's answer. */
  today: string;
  /** Called with the closure as the server saved it. */
  onMoved: (saved: Closure) => void;
  /** Called when the server says someone else cancelled the closure meanwhile (closure.not_active). */
  onGone: () => void;
  onCancel: () => void;
}) {
  const t = useTranslations("shopSettings");
  const apiError = useTranslations("apiError");
  const codes = useCodeWords();
  const { fieldMessages } = useApiErrorWords();
  const online = useOnline();
  const store = useQueryClient();

  // The earliest last day the server takes: never before the first day, nor before yesterday (see the top of this
  // file). Days as text sort as days do ("2026-11-22").
  const yesterday = dayBefore(today);
  const earliest =
    closure.first_day > yesterday ? closure.first_day : yesterday;
  const [day, setDay] = useState(closure.last_day);
  const [reason, setReason] = useState("");
  const [own, setOwn] = useState<Checks>({});

  const move = useMutation({
    mutationFn: (sent: { last_day: string; reason: string }) =>
      answerOf(
        api.POST("/api/v1/shops/closures/{id}/last-day/", {
          params: { path: { id: closure.id } },
          body: sent,
        }),
      ),
    onSuccess: (saved) => {
      // Its new days at once, or out of the list if it now ends before today; then the list asks again (closures.ts).
      keepClosure(store, saved);
      void store.invalidateQueries({ queryKey: CLOSURES });
      onMoved(saved);
    },
    onError: (error) => {
      // Someone else cancelled it meanwhile: it has left the list, so the list is read again, and the section says why
      // its line is gone (see the top of this file).
      if (
        error instanceof ApiRefusal &&
        error.body.code === "closure.not_active"
      ) {
        dropClosure(store, closure.id);
        void store.invalidateQueries({ queryKey: CLOSURES });
        onGone();
      }
      // Days another closure has, maybe one added meanwhile that the page doesn't show yet: the list is read again.
      if (error instanceof ApiRefusal && error.body.code === "closure.overlaps")
        void store.invalidateQueries({ queryKey: CLOSURES });
    },
  });

  function send(event: FormEvent) {
    // The browser would send the form itself and load a new page; the app sends it instead.
    event.preventDefault();
    // Each tap shows only what it finds, never the last send's refusal (setting-form.tsx).
    move.reset();
    const checks: Checks = {};
    if (day === "") checks.last_day = "required";
    // Before the first day, its order is what is wrong, as the server says it: a day of the past is then beside the
    // point (change_last_day).
    else if (day < closure.first_day)
      checks.last_day = "closure.ends_before_it_starts";
    else if (day < yesterday) checks.last_day = "closure.date_past";
    else if (day === closure.last_day) checks.last_day = SAME_DAY;
    // Spaces alone are no reason, as the server says too (rule 7: who, when and why).
    if (reason.trim() === "") checks.reason = "closure.reason_required";
    setOwn(checks);
    if (Object.keys(checks).length > 0) return;
    move.mutate({ last_day: day, reason });
  }

  // Where each refusal shows: beside its box, the form's own first, then the server's; one of a field the form has no
  // box for, a newer server's, above the buttons in its own sentence; one with no field, ApiErrorAlert's
  // (closure-form.tsx).
  const byField = fieldMessages(move.error);
  const said = (code?: string) =>
    code === undefined
      ? undefined
      : code === SAME_DAY
        ? t("closures.sameLastDay")
        : codeMessage(codes, code);
  const noBox = Object.entries(byField)
    .filter(([field]) => !ON_A_BOX.has(field))
    .map(([, sentence]) => sentence);

  return (
    // noValidate: the browser's own checks would speak its language, not the shop's.
    <form noValidate onSubmit={send} className="grid gap-6">
      <Field
        label={t("closures.newLastDay")}
        // Its last day now, so the owner sees what he changes.
        hint={t("closures.newLastDayHint", {
          last: formatDay(closure.last_day),
        })}
        error={said(own.last_day) ?? byField.last_day}
        type="date"
        // The phone's calendar offers nothing before the earliest day the server takes (see the top of this file). On
        // the demo it still offers yesterday, which opens today, and the server refuses it there, beside this box, as
        // a person's change of today (demo.closures_from_tomorrow).
        min={earliest}
        value={day}
        onChange={(event) => setDay(event.target.value)}
        // The person just asked for this form: the keyboard starts in its first box, where the button was.
        autoFocus
      />
      <Field
        label={t("closures.reason")}
        hint={t("closures.reasonHint")}
        error={said(own.reason) ?? byField.reason}
        value={reason}
        onChange={(event) => setReason(event.target.value)}
        autoComplete="off"
        // As the server takes it (ClosureLastDaySerializer, 500 characters).
        maxLength={500}
      />
      {noBox.length > 0 ? (
        <Alert kind="danger">
          {/* The icon says what the title says, so a screen reader skips it (api-error-alert.tsx). */}
          <CircleAlert aria-hidden="true" />
          <AlertTitle>{apiError("title")}</AlertTitle>
          <AlertDescription>{noBox.join(" ")}</AlertDescription>
        </Alert>
      ) : null}
      {/* What no field names: days another closure has, no network, the server's own problem. Shown
          beside a box's refusal too, when the server sends both (aboutTheWholeRequest, src/api/refusal.ts). */}
      <ApiErrorAlert error={aboutTheWholeRequest(move.error)} />
      <div className="flex flex-wrap gap-3">
        {/* Off while it is sent, so a second tap sends nothing, and while offline, so nothing waits unsent while it
            looks done. */}
        <Button type="submit" disabled={move.isPending || !online}>
          {t("form.save")}
        </Button>
        <Button kind="second" onClick={onCancel}>
          {t("form.cancel")}
        </Button>
      </div>
    </form>
  );
}
