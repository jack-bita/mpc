// closure-cancel.tsx — Ondoa: take a closure off before its first day, with a reason (ATT-9, ATT-8's cancel_closure).
// Opens under the closure's line on Siku duka limefungwa, for someone holding settings.manage on the whole shop, while
// its first day is today or later: once a day of it has passed, that day stays closed, and the owner moves the last
// day instead (closure.started).
//
// Its days open again, and are worked and paid as any other. The closure isn't deleted (rule 7): the server keeps it,
// cancelled, and its audit trail keeps who, when and why. So the reason is asked every time (closure.reason_required),
// said at once if the box is empty, and sent as typed; the server takes the spaces off.
//
// A cancel carries no id of its own, as an add does: the closure's id names it. So a cancel sent again, whose first
// answer the network lost, is refused as closure.not_active, as the first one already cancelled it. The page reads
// that as done (ATT-8's review): the closure is cancelled either way, by this tap's lost answer or by someone else's
// cancel a moment before. It says so as it would for its own, and the list is read again, without the closure.
//
// The rest of the server's refusals have no box but the reason's, and show above the buttons: closure.started (its
// first day passed while the page was open), and on the demo, a person's cancel of one that starts today
// (demo.closures_from_tomorrow), as today's demo stays as the seed made it for every visitor.
//
// "use client": it asks use-intl for words (use-client.test.ts), and calls the server.
"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CircleAlert } from "lucide-react";
import { type FormEvent, useId, useState } from "react";
import { useTranslations } from "use-intl";

import { api } from "@/api/client";
import { useApiErrorWords } from "@/api/errors";
import { answerOf, ApiRefusal } from "@/api/refusal";
import { ApiErrorAlert } from "@/components/api-error-alert";
import { Alert, AlertDescription, AlertTitle } from "@/components/design/alert";
import { Button } from "@/components/design/button";
import { Field } from "@/components/design/field";
import { codeMessage, useCodeWords } from "@/i18n/codes";
import { useOnline } from "@/offline/network";

import { type Closure, CLOSURES, dropClosure, useDaysOf } from "./closures";

export function ClosureCancel({
  closure,
  onCancelled,
  onCancel,
}: {
  closure: Closure;
  /** Called once the closure is cancelled: by this form, or before it, as a lost answer's (see the top of this file). */
  onCancelled: () => void;
  onCancel: () => void;
}) {
  const t = useTranslations("shopSettings");
  const apiError = useTranslations("apiError");
  const codes = useCodeWords();
  const { fieldMessages } = useApiErrorWords();
  const online = useOnline();
  const store = useQueryClient();
  const daysOf = useDaysOf();
  // The question's id, which the form's answer names (aria-describedby), as side-switch.tsx's: a screen reader says
  // which closure Ondoa removes, not "Ondoa, button" alone.
  const question = useId();
  const [reason, setReason] = useState("");
  // The form's own check of the reason, as the code the server would send.
  const [blank, setBlank] = useState(false);

  const cancel = useMutation({
    mutationFn: async (sent: string) => {
      try {
        await answerOf(
          api.POST("/api/v1/shops/closures/{id}/cancel/", {
            params: { path: { id: closure.id } },
            body: { reason: sent },
          }),
        );
      } catch (error) {
        // Already cancelled: done, not refused (see the top of this file).
        if (
          error instanceof ApiRefusal &&
          error.body.code === "closure.not_active"
        )
          return;
        throw error;
      }
    },
    onSuccess: () => {
      // Out of the list at once, then the list asks again: a cancelled closure never stays on the page (closures.ts).
      dropClosure(store, closure.id);
      void store.invalidateQueries({ queryKey: CLOSURES });
      onCancelled();
    },
  });

  function send(event: FormEvent) {
    // The browser would send the form itself and load a new page; the app sends it instead.
    event.preventDefault();
    // Each tap shows only what it finds, never the last send's refusal (setting-form.tsx).
    cancel.reset();
    const empty = reason.trim() === "";
    setBlank(empty);
    if (empty) return;
    cancel.mutate(reason);
  }

  // The reason's refusal beside its box, the form's own first; one of a field the form has no box for, a newer
  // server's, above the buttons in its own sentence; the rest, with no field, ApiErrorAlert's (closure-form.tsx).
  const byField = fieldMessages(cancel.error);
  const noBox = Object.entries(byField)
    .filter(([field]) => field !== "reason")
    .map(([, sentence]) => sentence);
  const aboutAField = Object.keys(byField).length > 0;

  return (
    // noValidate: the browser's own checks would speak its language, not the shop's.
    <form noValidate onSubmit={send} className="grid gap-6">
      {/* What Ondoa does, before the owner presses it: the shop opens on those days. */}
      <p id={question} className="text-lg">
        {t("closures.removeAsk", {
          name: closure.name,
          days: daysOf(closure),
        })}
      </p>
      <Field
        label={t("closures.reason")}
        hint={t("closures.reasonHint")}
        error={
          blank ? codeMessage(codes, "closure.reason_required") : byField.reason
        }
        value={reason}
        onChange={(event) => setReason(event.target.value)}
        // The person just asked for this form: the keyboard starts in its one box, where Ondoa was.
        autoFocus
        autoComplete="off"
        // As the server takes it (ClosureReasonSerializer, 500 characters).
        maxLength={500}
      />
      {noBox.length > 0 ? (
        <Alert kind="danger">
          {/* The icon says what the title says, so a screen reader skips it (api-error-alert.tsx). */}
          <CircleAlert aria-hidden="true" />
          <AlertTitle>{apiError("title")}</AlertTitle>
          <AlertDescription>{noBox.join(" ")}</AlertDescription>
        </Alert>
      ) : (
        // What no field names: a closure already begun, the demo's today, no network, the server's own problem.
        <ApiErrorAlert error={aboutAField ? null : cancel.error} />
      )}
      <div className="flex flex-wrap gap-3">
        {/* The colour of a change that can't be called back: the days open at once. Off while it is sent, so a second
            tap sends nothing, and while offline, so nothing waits unsent while it looks done. */}
        <Button
          type="submit"
          kind="danger"
          aria-describedby={question}
          disabled={cancel.isPending || !online}
        >
          {t("closures.remove")}
        </Button>
        <Button kind="second" onClick={onCancel}>
          {t("form.cancel")}
        </Button>
      </div>
    </form>
  );
}
