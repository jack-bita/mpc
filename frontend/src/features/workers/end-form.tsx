// end-form.tsx — Ondoa (PPL-8): take a role or an extra key away from a worker, with a reason, through PPL-7's routes
// (POST …/staff/{id}/end-role/ and …/end-key/). Opens under the worker's roles and keys (worker-roles.tsx), its title
// naming what goes: "Ondoa Muuzaji (Dawa) kwa Juma".
//
// Taking away is an edit, never a delete (rule 7): the server keeps the row, marked ended, with who, when and this
// reason, and the worker holds none of it from then on; their laptop drops it at its next sync (PPL-7). Who may is
// Simamisha's rule (Jack, PPL-7: A): staff.manage on the whole shop, never one's own (staff.own), never from someone
// holding a key the person acting lacks (staff.more_keys), an owner's only by the superuser (staff.superuser_only).
//
// Sababu is required. Empty, or spaces alone, is said at once, beside its box, in the server's own sentence, and
// nothing is sent: staff.reason_required, as the server answers a blank reason (StaffReasonSerializer lets it through
// for the service to refuse with that code, so the card's `blank` never comes). The server's own staff.reason_required
// comes as the whole request's code, and shows beside the box all the same (worker-actions.tsx).
//
// An end has no id of its own (PPL-7's review): an end whose answer the network lost, sent again, hears
// role.already_ended or permission.already_ended. That is taken as done: the worker is read again, and the done line
// said, as what the person asked for has happened, whoever got there first. staff.left closes the form, says it, and
// reads the worker again, as Simamisha's form does. Every other refusal shows above the buttons, in its sentence:
// staff.own, staff.superuser_only, staff.more_keys, demo.people_fixed (the seed's people keep their roles on the demo),
// and the bare 403 of a person without staff.manage.
//
// "use client": it asks use-intl for words (use-client.test.ts), and calls the server.
"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { useTranslations } from "use-intl";

import { api } from "@/api/client";
import { useApiErrorWords } from "@/api/errors";
import { answerOf, ApiRefusal } from "@/api/refusal";
import { ApiErrorAlert } from "@/components/api-error-alert";
import { Button } from "@/components/design/button";
import { Field } from "@/components/design/field";
import { codeMessage, useCodeWords } from "@/i18n/codes";
import { useOnline } from "@/offline/network";

import { aboutTheChange, keepWorker, type Worker, WORKERS } from "./workers";

/** What goes: one of the worker's roles or keys, by the id of its row, and its words with its side. */
export type Ending = { kind: "role" | "key"; id: string; words: string };

/** The codes that say the end happened already: taken as done (see the top). */
const ENDED_ALREADY = new Set([
  "role.already_ended",
  "permission.already_ended",
]);

/** The server's code for an empty reason, shown beside Sababu. */
const REASON_REQUIRED = "staff.reason_required";

export function EndForm({
  worker,
  ending,
  onDone,
  onChangedMeanwhile,
  onCancel,
}: {
  worker: Worker;
  ending: Ending;
  /** Taken away: the line that says what, in the person's words. */
  onDone: (sentence: string) => void;
  /** Someone else changed the worker first: what the server's code says. */
  onChangedMeanwhile: (sentence: string) => void;
  onCancel: () => void;
}) {
  const t = useTranslations("workers.ending");
  const actionWords = useTranslations("workers.actions");
  const codes = useCodeWords();
  const { fieldMessages } = useApiErrorWords();
  const online = useOnline();
  const store = useQueryClient();
  const [reason, setReason] = useState("");
  const [own, setOwn] = useState<string | undefined>(undefined);

  const done = t("done", { name: worker.display_name, what: ending.words });

  const end = useMutation({
    mutationFn: (why: string) => {
      const params = { path: { id: worker.id } };
      return ending.kind === "role"
        ? answerOf(
            api.POST("/api/v1/people/staff/{id}/end-role/", {
              params,
              body: { role_given: ending.id, reason: why },
            }),
          )
        : answerOf(
            api.POST("/api/v1/people/staff/{id}/end-key/", {
              params,
              body: { key: ending.id, reason: why },
            }),
          );
    },
    onSuccess: (changed) => {
      // The worker as they are now, on their page and in the list at once, then both asked again (workers.ts).
      keepWorker(store, changed);
      void store.invalidateQueries({ queryKey: WORKERS });
      onDone(done);
    },
    onError: (error) => {
      if (!(error instanceof ApiRefusal)) return;
      // Already ended, by this end sent before or by someone else: done, and the worker read again (see the top).
      if (ENDED_ALREADY.has(error.body.code)) {
        void store.invalidateQueries({ queryKey: WORKERS });
        onDone(done);
      } else if (error.body.code === "staff.left") {
        void store.invalidateQueries({ queryKey: WORKERS });
        onChangedMeanwhile(codeMessage(codes, error.body.code));
      }
    },
  });

  function send(event: FormEvent) {
    // The browser would send the form itself and load a new page; the app sends it instead.
    event.preventDefault();
    // The last send's refusal is about what was sent then: each tap shows only what it finds (setting-form.tsx).
    end.reset();
    // Spaces alone are no reason, as the server says too.
    const why = reason.trim();
    const check = why === "" ? REASON_REQUIRED : undefined;
    setOwn(check);
    if (check !== undefined) return;
    end.mutate(why);
  }

  // Where each refusal shows: beside Sababu, the form's own first, then the server's, by its code or its field. The
  // codes that close the form show nothing here; everything else is ApiErrorAlert's, above the buttons.
  const code =
    end.error instanceof ApiRefusal ? end.error.body.code : undefined;
  const closes =
    code !== undefined && (ENDED_ALREADY.has(code) || code === "staff.left");
  const besideBox = code === REASON_REQUIRED;
  // A field's refusal the form has no box for (`role_given`, `key`) shows above, never nowhere (aboutTheChange).
  const above =
    closes || besideBox ? null : aboutTheChange(end.error, ["reason"]);

  return (
    // noValidate: the browser's own checks would speak its language, not the shop's.
    <form noValidate onSubmit={send} className="grid gap-6">
      <h2 className="text-lg font-semibold">
        {t("title", { what: ending.words, name: worker.display_name })}
      </h2>
      <Field
        label={actionWords("reason")}
        hint={actionWords("reasonHint")}
        error={
          (own === undefined ? undefined : codeMessage(codes, own)) ??
          (besideBox ? codeMessage(codes, REASON_REQUIRED) : undefined) ??
          fieldMessages(end.error).reason
        }
        value={reason}
        onChange={(event) => setReason(event.target.value)}
        autoComplete="off"
        // As the ended row keeps it (StaffReasonSerializer, 500 characters).
        maxLength={500}
        // The person just asked for this form: the keyboard starts in its box, where the button was.
        autoFocus
      />
      {/* Who may (staff.own, staff.more_keys, staff.superuser_only, demo.people_fixed), no network, the server's own
          problem. */}
      <ApiErrorAlert error={above} />
      <div className="flex flex-wrap gap-3">
        {/* Switched off while it is sent, so a second tap sends nothing, and while offline, so nothing waits unsent
            while it looks done (setting-form.tsx). Danger, as Ameondoka: a worker loses what they could do. */}
        <Button type="submit" kind="danger" disabled={end.isPending || !online}>
          {actionWords("save")}
        </Button>
        <Button kind="second" onClick={onCancel}>
          {actionWords("cancel")}
        </Button>
      </div>
    </form>
  );
}
