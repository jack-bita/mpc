// flag-note.tsx — Eleza, Imetatuliwa and Si tatizo: a note on a flag, in a sheet over its page (CTRL-4), as Jack
// pictured it (24 Nov 2026):
//
//   ┌──────────────────────────────────────────┐
//   │ Imetatuliwa                              │
//   │ Ikifungwa, tofauti hii haifunguliwi tena.│
//   │ Maelezo [ Nimezungumza naye            ] │
//   │ [ Ghairi ]              [ Funga tofauti ]│
//   └──────────────────────────────────────────┘
//
// Eleza keeps the words and leaves the flag waiting; the other two close it for good, so the sheet says so before
// anyone taps. Who wrote them and when is the server's to keep (02 §13).
//
// The note's id is made as the sheet opens and sent with every try, so one sent again after a lost answer is written
// once (ADR-0007). On the demo the words are one of three ready ones to tap (the answer's ready_notes), as typed ones
// would show to every visitor after them (Jack, ATT-6: A). The server's refusals show beside the box, or above the
// buttons: someone closed it meanwhile, the flag names this person, no network, the server's problem; and the flag is
// read again, so the page behind shows it as it now is.
//
// "use client": it asks use-intl for words (use-client.test.ts), and calls the server.
"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslations } from "use-intl";

import { api } from "@/api/client";
import { useApiErrorWords } from "@/api/errors";
import { aboutTheWholeRequest, answerOf } from "@/api/refusal";
import { ApiErrorAlert } from "@/components/api-error-alert";
import { Choice } from "@/components/design/choice";
import { Field } from "@/components/design/field";
import { Sheet } from "@/components/design/sheet";
import { codeMessage, useCodeWords } from "@/i18n/codes";
import { newId } from "@/lib/ids";
import { useOnline } from "@/offline/network";

import { type Flag, FLAGS, type FlagAction, flagKey } from "./flags";
import { useReadyNoteWords } from "./flag-words";

/** The server's longest note (FlagNote.text, 500 characters). */
const NOTE_LONGEST = 500;

/** Each action's own route: three, so each is an address of the API's description, typed to its last word. */
const SEND = {
  explain: (id: string, body: { id: string; text: string }) =>
    api.POST("/api/v1/control/flags/{id}/explain/", {
      params: { path: { id } },
      body,
    }),
  resolve: (id: string, body: { id: string; text: string }) =>
    api.POST("/api/v1/control/flags/{id}/resolve/", {
      params: { path: { id } },
      body,
    }),
  dismiss: (id: string, body: { id: string; text: string }) =>
    api.POST("/api/v1/control/flags/{id}/dismiss/", {
      params: { path: { id } },
      body,
    }),
} as const;

export function FlagNoteSheet({
  flag,
  action,
  onDone,
  onClose,
  finalFocus,
}: {
  flag: Flag;
  action: FlagAction;
  /** The note is kept, and the flag as the server now has it is in the store. */
  onDone: () => void;
  onClose: () => void;
  finalFocus: () => HTMLElement | null;
}) {
  const t = useTranslations("flags.act");
  const codes = useCodeWords();
  const readyWords = useReadyNoteWords();
  const { fieldMessages } = useApiErrorWords();
  const online = useOnline();
  const store = useQueryClient();
  // Made once, as the sheet opens, so every try of this note carries the same id.
  const [noteId] = useState(() => newId());
  const [text, setText] = useState("");
  // The form's own check, as the server would refuse it, shown once the person has tried to send.
  const [tried, setTried] = useState(false);

  const write = useMutation({
    mutationFn: (words: string) =>
      answerOf(SEND[action](flag.id, { id: noteId, text: words })),
    onSuccess: async (moved) => {
      // First, any read of the flag still on its way, as a lost send asks for one: the server may have read it before
      // this note, and its answer, landing later, would put a closed flag back with its three buttons (my-settings.tsx,
      // UI-9's review; CTRL-4's). Cancelled, its answer is dropped.
      await store.cancelQueries({ queryKey: flagKey(flag.id) });
      // The flag on its page at once, from the server's own answer; the lists read again, as it may have moved from
      // one tab to the other.
      store.setQueryData<Flag>(flagKey(flag.id), moved);
      void store.invalidateQueries({ queryKey: [...FLAGS, "list"] });
      onDone();
    },
    // Closed by someone else meanwhile, or kept though its answer was lost: the page behind reads it as it now is.
    onError: () => void store.invalidateQueries({ queryKey: FLAGS }),
  });

  function send() {
    // Each try shows only what it finds, never the last one's refusal (setting-form.tsx).
    write.reset();
    setTried(true);
    if (text.trim() === "") return;
    write.mutate(text);
  }

  // The form's own check first, then the server's, beside the box; the rest above the buttons (void-tap.tsx).
  const textError =
    tried && text.trim() === ""
      ? codeMessage(codes, "flag.note_required")
      : fieldMessages(write.error).text;
  // A refusal of fields this sheet has no box for, as an id taken, is about the whole note: shown above, never nowhere.
  const above =
    textError === undefined ? write.error : aboutTheWholeRequest(write.error);

  return (
    <Sheet
      open
      onClose={onClose}
      title={t(`${action}.title`)}
      description={t(`${action}.about`)}
      actionLabel={t(`${action}.save`)}
      onAction={send}
      busy={write.isPending}
      // Offline, nothing is sent, so nothing waits unsent while it looks done (void-tap.tsx).
      actionDisabled={!online}
      finalFocus={finalFocus}
    >
      {flag.ready_notes.length > 0 ? (
        // On the demo: ready notes to tap, kept as their codes, said in words wherever they show.
        <Choice
          label={t("text")}
          hint={t("readyHint")}
          error={textError}
          options={flag.ready_notes.map((code) => ({
            value: code,
            label: readyWords(code),
          }))}
          value={text === "" ? null : text}
          onValueChange={setText}
        />
      ) : (
        <Field
          label={t("text")}
          hint={t("textHint")}
          error={textError}
          value={text}
          onChange={(event) => setText(event.target.value)}
          autoComplete="off"
          maxLength={NOTE_LONGEST}
        />
      )}
      <ApiErrorAlert error={above} />
    </Sheet>
  );
}
