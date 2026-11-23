// remove-photo-sheet.tsx — Ondoa picha (PPL-9): take a worker's photo off, with a reason, through POST
// …/staff/{id}/remove-photo/. Opens from the card's own Ondoa picha (worker-photo.tsx), in a sheet over the worker's
// page (sheet.tsx), titled "Ondoa picha ya Asha"; then Sababu, Ghairi and Ondoa picha, red, as Jack drew it: the photo's
// file goes for good. Its row stays on the server, with who, when and this reason (rule 7).
//
// It names the photo it takes off, the one that was on the screen as the button was tapped, kept for as long as the
// sheet is open whatever the page reads meanwhile: a newer one the owner set in between, which nobody here saw, is
// refused by the server (409 version_conflict) and stays. The sheet then closes, the card says the photo changed, and
// the worker is read again, so the card shows the one there now. A photo already gone is done: the server answers with
// the worker as they are, so a tap sent again after an answer the network lost says the same line.
//
// Sababu is required. Empty, or spaces alone, is said at once, beside its box, in the server's own sentence, and
// nothing is sent; the server's own staff.reason_required comes as the whole request's code, and shows beside the box
// all the same (end-form.tsx). staff.left closes the sheet, says it, and reads the worker again. Every other refusal
// shows above the sheet's buttons, the reason kept: who may (staff.own, staff.superuser_only, staff.more_keys), and on
// the demo demo.people_fixed.
//
// "use client": it asks use-intl for words (use-client.test.ts), and calls the server.
"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslations } from "use-intl";

import { api } from "@/api/client";
import { useApiErrorWords } from "@/api/errors";
import { answerOf, ApiRefusal } from "@/api/refusal";
import { ApiErrorAlert } from "@/components/api-error-alert";
import { Field } from "@/components/design/field";
import { Sheet } from "@/components/design/sheet";
import { codeMessage, useCodeWords } from "@/i18n/codes";
import { useOnline } from "@/offline/network";

import { aboutTheChange, keepWorker, type Worker, WORKERS } from "./workers";

/** The server's code for an empty reason, shown beside Sababu. */
const REASON_REQUIRED = "staff.reason_required";

/** The codes that say someone else changed the worker first: the sheet closes, and the card says it. */
const CHANGED_MEANWHILE = new Set(["version_conflict", "staff.left"]);

export function RemovePhotoSheet({
  worker,
  photo,
  onDone,
  onChangedMeanwhile,
  onCancel,
  finalFocus,
}: {
  worker: Worker;
  /** The photo that was on the screen as the button was tapped, by its id. */
  photo: string;
  /** Taken off: the worker as the server answered. */
  onDone: (worker: Worker) => void;
  /** Someone else changed the worker first: what to say on the card. */
  onChangedMeanwhile: (sentence: string) => void;
  /** Ghairi or Esc. */
  onCancel: () => void;
  /** Where the keyboard goes as the sheet goes (sheet.tsx). */
  finalFocus: () => HTMLElement | null;
}) {
  const t = useTranslations("workers.photo");
  const actionWords = useTranslations("workers.actions");
  const codes = useCodeWords();
  const { fieldMessages } = useApiErrorWords();
  const online = useOnline();
  const store = useQueryClient();
  const [reason, setReason] = useState("");
  const [own, setOwn] = useState<string | undefined>(undefined);

  const remove = useMutation({
    mutationFn: (why: string) =>
      answerOf(
        api.POST("/api/v1/people/staff/{id}/remove-photo/", {
          params: { path: { id: worker.id } },
          body: { photo, reason: why },
        }),
      ),
    onSuccess: (changed) => {
      // The worker as they are now, on their page and in the list at once, then both asked again (workers.ts).
      keepWorker(store, changed);
      void store.invalidateQueries({ queryKey: WORKERS });
      onDone(changed);
    },
    onError: (error) => {
      if (
        !(error instanceof ApiRefusal) ||
        !CHANGED_MEANWHILE.has(error.body.code)
      )
        return;
      void store.invalidateQueries({ queryKey: WORKERS });
      onChangedMeanwhile(
        error.body.code === "version_conflict"
          ? // Said of the photo, as the code's own sentence says only that something changed.
            t("changedMeanwhile", { name: worker.display_name })
          : codeMessage(codes, error.body.code),
      );
    },
  });

  /** The sheet's Ondoa picha, or Enter in its box: the sheet's own form stops the browser's send (sheet.tsx). */
  function send() {
    // The last send's refusal is about what was sent then: each tap shows only what it finds (setting-form.tsx).
    remove.reset();
    // Spaces alone are no reason, as the server says too.
    const why = reason.trim();
    const check = why === "" ? REASON_REQUIRED : undefined;
    setOwn(check);
    if (check !== undefined) return;
    remove.mutate(why);
  }

  // Where each refusal shows: beside Sababu, the form's own first, then the server's, by its code or its field. The
  // codes that close the sheet show nothing here; everything else is ApiErrorAlert's, above the sheet's buttons.
  const code =
    remove.error instanceof ApiRefusal ? remove.error.body.code : undefined;
  const besideBox = code === REASON_REQUIRED;
  const closes = code !== undefined && CHANGED_MEANWHILE.has(code);
  const above =
    closes || besideBox ? null : aboutTheChange(remove.error, ["reason"]);

  return (
    <Sheet
      open
      onClose={onCancel}
      title={t("removeTitle", { name: worker.display_name })}
      actionLabel={t("remove")}
      // Danger, as Ameondoka: the photo's file goes for good.
      actionKind="danger"
      onAction={send}
      // Held while it is sent, so a second tap sends nothing, and the sheet stays until its answer comes.
      busy={remove.isPending}
      // Offline, nothing is sent, so nothing waits unsent while it looks done (setting-form.tsx).
      actionDisabled={!online}
      finalFocus={finalFocus}
    >
      <Field
        label={actionWords("reason")}
        hint={actionWords("reasonHint")}
        error={
          (own === undefined ? undefined : codeMessage(codes, own)) ??
          (besideBox ? codeMessage(codes, REASON_REQUIRED) : undefined) ??
          fieldMessages(remove.error).reason
        }
        value={reason}
        onChange={(event) => setReason(event.target.value)}
        autoComplete="off"
        // As the photo's row keeps it (StaffReasonSerializer, 500 characters).
        maxLength={500}
        // The person just asked for this sheet: the keyboard starts in its box.
        autoFocus
      />
      {/* Who may (staff.own, staff.more_keys, staff.superuser_only, demo.people_fixed), no network, the server's own
          problem. */}
      <ApiErrorAlert error={above} />
    </Sheet>
  );
}
