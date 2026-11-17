// closure-form.tsx — Ongeza: close the whole shop from a first day to a last (ATT-9, ATT-8). Opens under Ongeza on
// Siku duka limefungwa, for someone holding settings.manage on the whole shop.
//
// Kuanzia, Hadi and Jina: a public holiday is one day, Siku ya Uhuru on 09/12; a funeral a span, 20/11 to 24/11. Hadi
// left empty is one day: the page sends Kuanzia's day as the last (ATT-9's default), so a holiday needs one date.
// Kuanzia starts empty: closing the shop makes every one of its days unpaid (02 §12), so the owner picks the day
// himself, and a quick Hifadhi never closes today by accident (ATT-9's default). Both boxes offer nothing before the
// shop's today, which the server sends with the list: a closure starts today or later (closure.date_past), so a
// funeral can still close the shop the same morning.
//
// What the form can see itself is said at once, in the server's own sentences, and nothing is sent: an empty Kuanzia,
// a day before today, a last day before the first, an empty name. The server checks the rest: days another closure
// already has (closure.overlaps), said above the buttons, as it is about the days together and no one box; and on the
// demo, a person's closure from today (demo.closures_from_tomorrow), said beside Kuanzia.
//
// The id is sent again with every try of the same days and name (ADR-0007): a send whose answer the network lost, tried
// again, gets the stored closure back, not a clash with itself. A changed day or name gets a new id, as the server
// answers a repeated id with the closure it stored, whatever the new send carries (setting-form.tsx). So if the first
// send was saved and only its answer lost, a changed try clashes with it (closure.overlaps), a closure the page doesn't
// show yet: on that refusal the list is read again, so the owner sees what his days clash with, his own closure among
// them, and changes it there (ATT-9's review).
//
// "use client": it asks use-intl for words (use-client.test.ts), and calls the server.
"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CircleAlert } from "lucide-react";
import { type FormEvent, useRef, useState } from "react";
import { useTranslations } from "use-intl";

import { api } from "@/api/client";
import { useApiErrorWords } from "@/api/errors";
import { answerOf, ApiRefusal } from "@/api/refusal";
import { ApiErrorAlert } from "@/components/api-error-alert";
import { Alert, AlertDescription, AlertTitle } from "@/components/design/alert";
import { Button } from "@/components/design/button";
import { Field } from "@/components/design/field";
import { codeMessage, useCodeWords } from "@/i18n/codes";
import { newId } from "@/lib/ids";
import { useOnline } from "@/offline/network";

import { type Closure, CLOSURES, keepClosure } from "./closures";

// The fields with a box, beside which their refusals show. A refusal of any other field shows above the buttons.
const ON_A_BOX = new Set(["first_day", "last_day", "name"]);

/** The form's own checks, by box, as the codes the server would send. */
type Checks = { first_day?: string; last_day?: string; name?: string };

/** What the form can see is wrong before sending: `first` and `last` as the boxes hold them ("2026-11-20"), with an
 * empty Hadi already read as Kuanzia's day. Days as text sort as days do. */
function checksOf(first: string, last: string, name: string, today: string) {
  const checks: Checks = {};
  if (first === "") checks.first_day = "required";
  else if (first < today) checks.first_day = "closure.date_past";
  // Only once there is a first day to compare with: an empty Kuanzia is said once, beside its own box.
  if (first !== "" && last < first)
    checks.last_day = "closure.ends_before_it_starts";
  // Spaces alone are no name, as the server says too.
  if (name.trim() === "") checks.name = "closure.name_blank";
  return checks;
}

export function ClosureForm({
  today,
  onSaved,
  onCancel,
}: {
  /** The shop's today, from the server's answer: the first day a closure may start. */
  today: string;
  onSaved: (closure: Closure) => void;
  onCancel: () => void;
}) {
  const t = useTranslations("shopSettings");
  const apiError = useTranslations("apiError");
  const codes = useCodeWords();
  const { fieldMessages } = useApiErrorWords();
  const online = useOnline();
  const store = useQueryClient();

  // The last send: its id, and what it carried, so a try of the same keeps its id (see the top of this file).
  const lastSend = useRef<{ id: string; carried: string } | null>(null);
  const [first, setFirst] = useState("");
  const [last, setLast] = useState("");
  const [name, setName] = useState("");
  const [own, setOwn] = useState<Checks>({});

  const save = useMutation({
    mutationFn: (body: {
      id: string;
      first_day: string;
      last_day: string;
      name: string;
    }) => answerOf(api.POST("/api/v1/shops/closures/", { body })),
    onSuccess: (closure) => {
      // In its place at once, soonest first, then the list asks again (closures.ts).
      keepClosure(store, closure);
      void store.invalidateQueries({ queryKey: CLOSURES });
      onSaved(closure);
    },
    onError: (error) => {
      // Days another closure has: the list is read again, so that closure shows (see the top of this file).
      if (error instanceof ApiRefusal && error.body.code === "closure.overlaps")
        void store.invalidateQueries({ queryKey: CLOSURES });
    },
  });

  function send(event: FormEvent) {
    // The browser would send the form itself and load a new page; the app sends it instead.
    event.preventDefault();
    // The last send's refusal is about what was sent then: each tap shows only what it finds (setting-form.tsx).
    save.reset();
    // Hadi left empty is one day: Kuanzia's (see the top of this file).
    const lastDay = last === "" ? first : last;
    const checks = checksOf(first, lastDay, name, today);
    setOwn(checks);
    if (Object.keys(checks).length > 0) return;
    // As the server keeps it: the spaces around a name taken off.
    const named = name.trim();
    // The same id for a try of the same days and name; a new one once any of them changed.
    const carried = JSON.stringify([first, lastDay, named]);
    if (lastSend.current?.carried !== carried)
      lastSend.current = { id: newId(), carried };
    save.mutate({
      id: lastSend.current.id,
      first_day: first,
      last_day: lastDay,
      name: named,
    });
  }

  // Where each refusal shows: beside its box, the form's own first, then the server's. A refusal of a field the form
  // has no box for, a newer server's, shows above the buttons in its own sentence (setting-form.tsx). One about the
  // days together, with no field, as closure.overlaps, is ApiErrorAlert's, above the buttons too.
  const byField = fieldMessages(save.error);
  const said = (code?: string) =>
    code === undefined ? undefined : codeMessage(codes, code);
  const noBox = Object.entries(byField)
    .filter(([field]) => !ON_A_BOX.has(field))
    .map(([, sentence]) => sentence);
  const aboutAField = Object.keys(byField).length > 0;

  return (
    // noValidate: the browser's own checks would speak its language, not the shop's.
    <form noValidate onSubmit={send} className="grid gap-6">
      <Field
        label={t("closures.form.from")}
        hint={t("closures.form.fromHint")}
        error={said(own.first_day) ?? byField.first_day}
        type="date"
        // The phone's calendar offers nothing before the shop's today.
        min={today}
        value={first}
        onChange={(event) => setFirst(event.target.value)}
        // The person just asked for this form: the keyboard starts in its first box, where Ongeza was.
        autoFocus
      />
      <Field
        label={t("closures.form.to")}
        hint={t("closures.form.toHint")}
        error={said(own.last_day) ?? byField.last_day}
        type="date"
        // Nothing before Kuanzia's day, once there is one.
        min={first === "" ? today : first}
        value={last}
        onChange={(event) => setLast(event.target.value)}
      />
      <Field
        label={t("closures.form.name")}
        hint={t("closures.form.nameHint")}
        error={said(own.name) ?? byField.name}
        value={name}
        onChange={(event) => setName(event.target.value)}
        autoComplete="off"
        // As the server keeps it (Closure.name, 60 characters).
        maxLength={60}
      />
      {noBox.length > 0 ? (
        <Alert kind="danger">
          {/* The icon says what the title says, so a screen reader skips it (api-error-alert.tsx). */}
          <CircleAlert aria-hidden="true" />
          <AlertTitle>{apiError("title")}</AlertTitle>
          <AlertDescription>{noBox.join(" ")}</AlertDescription>
        </Alert>
      ) : (
        // What no field names: days another closure has, no network, no key, the server's own problem.
        <ApiErrorAlert error={aboutAField ? null : save.error} />
      )}
      <div className="flex flex-wrap gap-3">
        {/* Switched off while it is sent, so a second tap sends nothing, and while offline, so nothing waits unsent
            while it looks done (setting-form.tsx); the id would save it once anyway. */}
        <Button type="submit" disabled={save.isPending || !online}>
          {t("form.save")}
        </Button>
        <Button kind="second" onClick={onCancel}>
          {t("form.cancel")}
        </Button>
      </div>
    </form>
  );
}
