// password-form.tsx — Nenosiri la muda (PPL-12): a first or forgotten password for a worker who works from their own
// phone, set face to face, through AUTH-6's POST /api/v1/people/staff/{id}/temporary-password/, which answers 204 and
// nothing else. Opens on the Kuingia card (worker-logins.tsx).
//
// Baba types a password for Asha, with Sababu, which the audit trail keeps with who and when (T3); then tells it to
// her. She logs in with her phone number or her email, and the office makes her choose her own before anything else
// (ADR-0038, OfficeFrame). The line after says so, with her phone as the shop writes it. The page never sees an email
// (StaffSerializer), so for a worker with no phone the form says to add one with Badilisha first, as a hint, not a
// block: one with an email still logs in, and the server refuses one with neither (password.no_login_name), which
// shows above the boxes.
//
// What the form sees, it says at once, beside its box, and sends nothing: an empty password (blank), a reason of only
// spaces (staff.reason_required). The password's own checks (too short, too common, too like her name or phone…) are
// the server's, beside Nenosiri; who may (password.own, password.superuser_only, password.more_keys), staff.left and
// demo.logins_fixed above the buttons, with no network and the server's own problems.
//
// The password is a secret: the change keeps nothing in the store once it is done (gcTime: 0, UI-5), as the store is
// shared by everyone who uses the phone; and the boxes go with the form when it closes, either way.
//
// "use client": it asks use-intl for words (use-client.test.ts), and calls the server.
"use client";

import { useMutation } from "@tanstack/react-query";
import { type FormEvent, useEffect, useRef, useState } from "react";
import { useTranslations } from "use-intl";

import { api } from "@/api/client";
import { useApiErrorWords } from "@/api/errors";
import { aboutTheWholeRequest, answerOf, ApiRefusal } from "@/api/refusal";
import { ApiErrorAlert } from "@/components/api-error-alert";
import { Button } from "@/components/design/button";
import { Field } from "@/components/design/field";
import { PasswordField } from "@/components/design/password-field";
import { codeMessage, useCodeWords } from "@/i18n/codes";
import { useOnline } from "@/offline/network";

import type { Worker } from "./workers";

/** The whole request's code about Sababu: the service raises it with no field, after the serializer's checks. */
const ABOUT_THE_REASON = "staff.reason_required";

/** The code that shows above the boxes, as it is about the worker, not what was typed: no phone and no email. */
const ABOVE_THE_BOXES = "password.no_login_name";

/** The form's own checks, by box, as the codes the server would send. */
type Checks = { password?: "blank"; reason?: typeof ABOUT_THE_REASON };

export function PasswordForm({
  worker,
  onDone,
  onCancel,
}: {
  worker: Worker;
  /** Set: the server answered 204, and nothing more. */
  onDone: () => void;
  onCancel: () => void;
}) {
  const t = useTranslations("workers.logins");
  const actions = useTranslations("workers.actions");
  const codes = useCodeWords();
  const { fieldMessages } = useApiErrorWords();
  const online = useOnline();
  const [password, setPassword] = useState("");
  const [reason, setReason] = useState("");
  const [own, setOwn] = useState<Checks>({});

  // The title takes the keyboard as the form opens, so a screen reader says what opened where the button was.
  const title = useRef<HTMLHeadingElement>(null);
  useEffect(() => title.current?.focus(), []);

  const change = useMutation({
    mutationFn: (sending: { password: string; reason: string }) =>
      answerOf(
        api.POST("/api/v1/people/staff/{id}/temporary-password/", {
          params: { path: { id: worker.id } },
          body: sending,
        }),
      ),
    // Nothing of the password outlives the change in the store, which everyone on this phone shares (UI-5).
    gcTime: 0,
    // Nothing of the worker changed that the page shows: no read again.
    onSuccess: () => onDone(),
  });

  function send(event: FormEvent) {
    // The browser would send the form itself and load a new page; the app sends it instead.
    event.preventDefault();
    // The last send's refusal is about what was sent then: each tap shows only what it finds (setting-form.tsx).
    change.reset();
    // Spaces alone are no reason, as the server says too. The password goes as typed: the server takes the spaces
    // off its ends itself, as allauth's login does (set_temporary_password).
    const why = reason.trim();
    const checks: Checks = {};
    if (password === "") checks.password = "blank";
    if (why === "") checks.reason = ABOUT_THE_REASON;
    setOwn(checks);
    if (Object.keys(checks).length > 0) return;
    change.mutate({ password, reason: why });
  }

  // Where each refusal shows: beside its box, the form's own first, then the server's, by field or by its code; above
  // the boxes, no way to log in; everything else above the buttons.
  const code =
    change.error instanceof ApiRefusal ? change.error.body.code : undefined;
  const byField = fieldMessages(change.error);
  const sayCode = (shown?: string) =>
    shown === undefined ? undefined : codeMessage(codes, shown);
  const aboveTheBoxes = code === ABOVE_THE_BOXES ? change.error : null;
  const aboveTheButtons =
    code === ABOUT_THE_REASON || code === ABOVE_THE_BOXES
      ? null
      : aboutTheWholeRequest(change.error);

  return (
    // noValidate: the browser's own checks would speak its language, not the shop's.
    <form noValidate onSubmit={send} className="grid gap-6">
      <div className="grid gap-2">
        <h2
          ref={title}
          tabIndex={-1}
          className="text-lg font-semibold outline-none"
        >
          {t("passwordTitle", { name: worker.display_name })}
        </h2>
        <p>{t("passwordIntro", { name: worker.display_name })}</p>
        {/* A hint, not a block (see the top): the page can't see an email. */}
        {worker.phone === null ? (
          <p className="text-muted-foreground">
            {t("noPhone", { name: worker.display_name })}
          </p>
        ) : null}
      </div>
      <ApiErrorAlert error={aboveTheBoxes} />
      <PasswordField
        label={t("password")}
        error={sayCode(own.password) ?? byField.password}
        // "new-password", never "off", which phones ignore on a password box: with "off", one tap could fill in the
        // owner's own saved password, and Asha would be told it (PPL-12's review). A box for a new password is never
        // filled with a saved one. A browser may still offer to save what is typed; the owner says no.
        autoComplete="new-password"
        // As the route takes it (TemporaryPasswordSerializer, 128 characters).
        maxLength={128}
        value={password}
        onChange={(event) => setPassword(event.target.value)}
      />
      <Field
        label={actions("reason")}
        hint={actions("reasonHint")}
        error={
          sayCode(own.reason) ??
          (code === ABOUT_THE_REASON ? sayCode(code) : undefined) ??
          byField.reason
        }
        value={reason}
        onChange={(event) => setReason(event.target.value)}
        autoComplete="off"
        // As the audit line keeps it (TemporaryPasswordSerializer, 500 characters).
        maxLength={500}
      />
      {/* Who may (password.own, password.superuser_only, password.more_keys), staff.left, the demo, no network, the
          server's own problem. */}
      <ApiErrorAlert error={aboveTheButtons} />
      <div className="flex flex-wrap gap-3">
        {/* Switched off while it is sent, so a second tap sends nothing, and while offline, so nothing waits unsent
            while it looks done (setting-form.tsx). */}
        <Button type="submit" disabled={change.isPending || !online}>
          {actions("save")}
        </Button>
        <Button kind="second" onClick={onCancel}>
          {actions("cancel")}
        </Button>
      </div>
    </form>
  );
}
