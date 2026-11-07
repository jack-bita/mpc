// forgot-password.tsx — Umesahau nenosiri?: the two ways back in after a forgotten password (UI-5,
// ADR-0038, 03 §5.9).
//
// Most of the shop's people have a phone and no email, and an SMS costs money for each message: so a
// forgotten password is set again face to face. The owner types a temporary one, and the person chooses
// their own at the next login (AUTH-6). Anyone who has an email may also ask for a link, which opens
// /password-reset/ and works once, for an hour (AUTH-3).
//
// The server answers the same whether or not anyone here has that email, and sends nothing to a stranger:
// so the screen says only that a link went *if* the email has an account, never whether it has one.
//
// "use client": it asks use-intl for words, and calls the server.
"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { useForm } from "react-hook-form";
import { useTranslations } from "use-intl";
import { z } from "zod";

import { callAllauth } from "@/api/allauth";
import { useApiErrorWords } from "@/api/errors";
import { ApiErrorAlert } from "@/components/api-error-alert";
import { Button, ButtonLink } from "@/components/design/button";
import { Field } from "@/components/design/field";
import { codeMessage, useCodeWords } from "@/i18n/codes";

// The form's own word for something that isn't an email. Not a server's code, so its sentence is in the
// form's book (errors.test.ts lists only the server's).
const NOT_AN_EMAIL = "not_an_email";

// Only an @: the server's check of an email is Django's, and the form must never refuse one it takes. A
// phone typed here is the likely mistake, and the sentence above the form says what to do without one.
const FORGOT_FORM = z.object({
  email: z
    .string()
    .trim()
    .min(1, { error: "required" })
    .refine((email) => email.includes("@"), { error: NOT_AN_EMAIL }),
});
type ForgotForm = z.infer<typeof FORGOT_FORM>;

export function ForgotPassword() {
  const t = useTranslations("password.forgot");
  const words = useCodeWords();
  const { fieldMessages } = useApiErrorWords();

  const form = useForm<ForgotForm>({
    resolver: zodResolver(FORGOT_FORM),
    defaultValues: { email: "" },
  });

  const ask = useMutation({
    mutationFn: ({ email }: ForgotForm) =>
      callAllauth({
        method: "POST",
        route: "auth/password/request",
        body: { email },
      }),
    onError: () => form.setFocus("email"),
  });

  // The form's button is gone once the link is sent, and focus with it: it moves to the sentence that
  // says what happened, so a screen reader says it, and Tab goes on to the way back.
  const sentLine = useRef<HTMLParagraphElement>(null);
  useEffect(() => {
    if (ask.isSuccess) sentLine.current?.focus();
  }, [ask.isSuccess]);

  // The server's only word beside the box is Django's `invalid`, whose general sentence ("some fields
  // are wrong") reads oddly under one box: the form's own says what an email looks like.
  const server = fieldMessages(ask.error);
  function emailError(): string | undefined {
    const own = form.formState.errors.email?.message;
    if (own === NOT_AN_EMAIL) return t("notAnEmail");
    if (own) return codeMessage(words, own);
    if (server.email) return t("notAnEmail");
    return undefined;
  }
  const onABox = server.email !== undefined;

  return (
    <div className="flex max-w-md flex-col gap-6">
      <h1 className="text-2xl font-semibold">{t("title")}</h1>
      {/* The way most people get back in: first, as most have no email. */}
      <p>{t("noEmail")}</p>
      {ask.isSuccess ? (
        <>
          <p ref={sentLine} tabIndex={-1} className="outline-none">
            {t("sent")}
          </p>
          <div>
            <ButtonLink href="/login/" kind="second">
              {t("back")}
            </ButtonLink>
          </div>
        </>
      ) : (
        <>
          <p>{t("withEmail")}</p>
          {/* noValidate: the browser's own checks would speak its language, not the shop's. */}
          <form
            noValidate
            onSubmit={(event) =>
              void form.handleSubmit((values) => ask.mutate(values))(event)
            }
            className="grid gap-6"
          >
            <Field
              label={t("email")}
              error={emailError()}
              type="email"
              inputMode="email"
              autoComplete="email"
              autoCapitalize="none"
              autoCorrect="off"
              spellCheck={false}
              {...form.register("email")}
            />
            {/* What no box can show: too many links asked, no network. */}
            <ApiErrorAlert error={onABox ? null : ask.error} />
            <div className="flex flex-wrap gap-3">
              <Button type="submit" disabled={ask.isPending}>
                {t("send")}
              </Button>
              <ButtonLink href="/login/" kind="second">
                {t("back")}
              </ButtonLink>
            </div>
          </form>
        </>
      )}
    </div>
  );
}
