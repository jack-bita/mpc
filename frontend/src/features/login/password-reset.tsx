// password-reset.tsx — Weka nenosiri jipya: the page an email's reset link opens, at
// /password-reset/#<key> (UI-5, AUTH-3, ADR-0038, 03 §5.9).
//
// The key sits after the #, which a browser never sends to a server, so no log ever holds it
// (HEADLESS_FRONTEND_URLS, backend/config/settings/base.py). The page reads it from the address, then
// takes it out of the address bar and the browser's history at once: the key sets the person's password
// for the hour it works, and the next person at this browser, or its history, must not get it.
//
// Then, in turn:
//   the key is checked    GET auth/password/reset, with the key in X-Password-Reset-Key: a dead one
//                         (used already, older than an hour) says so before anyone types a password
//   the new password      typed twice (new-password.ts), sent with the key
//   done                  allauth answers 401, as a reset logs nobody in (AUTH-3), or 200 on a browser
//                         already logged in: either way, "log in with it now"
// A key that died meanwhile says so too, with the way to ask for another (forgot-password.tsx).
//
// "use client": it asks use-intl for words, reads the browser's address, and calls the server.
"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  type RefObject,
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
import { useForm } from "react-hook-form";
import { useTranslations } from "use-intl";
import { z } from "zod";

import { callAllauth } from "@/api/allauth";
import { useApiErrorWords } from "@/api/errors";
import { ApiRefusal } from "@/api/refusal";
import { ApiErrorAlert } from "@/components/api-error-alert";
import { Button, ButtonLink } from "@/components/design/button";
import { Field } from "@/components/design/field";
import { codeMessage, useCodeWords } from "@/i18n/codes";

import { NEW_PASSWORD, NOT_THE_SAME, TYPED_THE_SAME } from "./new-password";

const RESET_FORM = z.object(NEW_PASSWORD).refine(...TYPED_THE_SAME);
type ResetForm = z.infer<typeof RESET_FORM>;

// What follows the # in the address. As it is, never decoded: allauth's keys are letters, digits and
// dashes, and a broken escape would throw (client.ts reads its cookie the same way).
function addressKey(): string {
  return window.location.hash.slice(1);
}

// A link pasted into the same tab changes only what follows the #: the page follows it.
function onNewKey(listener: () => void): () => void {
  window.addEventListener("hashchange", listener);
  return () => window.removeEventListener("hashchange", listener);
}

/** The key the link brought: undefined while the page is built (no address exists then), null when the
 * link held none. Once read, it is taken out of the address bar and the history, and the page keeps its
 * own copy. */
function useTheLinksKey(): string | null | undefined {
  // useSyncExternalStore: React's way to read something kept outside React, as this-device.ts reads the
  // device's saved copy. The build knows no address (the last argument).
  const inTheAddress = useSyncExternalStore(
    onNewKey,
    addressKey,
    () => undefined,
  );
  const [kept, setKept] = useState<string | null>(null);
  // Kept as it is seen, while drawing: React's way to keep what an earlier draw saw. The address no
  // longer holds it once taken out below.
  if (inTheAddress && inTheAddress !== kept) setKept(inTheAddress);
  useEffect(() => {
    if (!kept || !addressKey()) return;
    // replaceState, not a new entry: Back must not bring the key back either. history.state is kept, as
    // Next.js's router keeps its own in it.
    window.history.replaceState(
      window.history.state,
      "",
      window.location.pathname + window.location.search,
    );
  }, [kept]);
  if (kept) return kept;
  return inTheAddress === undefined ? undefined : null;
}

/** Whether a refusal is about the link's key: used once already, or older than an hour. */
function aboutTheKey(error: unknown): boolean {
  return error instanceof ApiRefusal && error.body.fields.key !== undefined;
}

export function PasswordReset() {
  const t = useTranslations("password");
  const words = useCodeWords();
  const { fieldMessages } = useApiErrorWords();
  const key = useTheLinksKey();

  // Asked once: a key stays good or dead, and its answer isn't worth keeping. The store's name for it
  // leaves the key out, so it shows nowhere but in the request.
  const check = useQuery({
    queryKey: ["auth", "password-reset"],
    queryFn: () =>
      callAllauth({
        method: "GET",
        route: "auth/password/reset",
        headers: { "X-Password-Reset-Key": key ?? "" },
      }),
    enabled: Boolean(key),
    staleTime: Infinity,
    gcTime: 0,
  });

  const form = useForm<ResetForm>({
    resolver: zodResolver(RESET_FORM),
    defaultValues: { fresh: "", again: "" },
  });

  const reset = useMutation({
    mutationFn: ({ fresh }: ResetForm) =>
      callAllauth({
        method: "POST",
        route: "auth/password/reset",
        // Not trimmed: sent as typed, as the login sends it.
        body: { key: key ?? "", password: fresh },
        // Done, and nobody logged in (401); or done on a browser already logged in (200).
        done: [200, 401],
      }),
    // A refusal beside the new box: the keyboard goes back to it, to type again at once.
    onError: (error) => {
      if (error instanceof ApiRefusal && error.body.fields.password)
        form.setFocus("fresh");
    },
  });

  // The sentence that replaces the form, once it is done or the link is dead: focus moves to it, as the
  // button that had it is gone, so a screen reader says it, and Tab goes on to the way forward.
  const outcome = useRef<HTMLParagraphElement>(null);
  const dead = aboutTheKey(check.error) || aboutTheKey(reset.error);
  useEffect(() => {
    if (reset.isSuccess || dead) outcome.current?.focus();
  }, [reset.isSuccess, dead]);

  function whatShows() {
    // Not read yet: nothing, for the moment until the page has looked at its address.
    if (key === undefined) return null;
    if (key === null)
      return (
        <WayForward
          text={t("reset.noKey")}
          href="/forgot-password/"
          label={t("reset.askAgain")}
        />
      );
    if (dead)
      return (
        <WayForward
          outcome={outcome}
          text={codeMessage(words, "invalid_password_reset")}
          href="/forgot-password/"
          label={t("reset.askAgain")}
        />
      );
    if (reset.isSuccess)
      return (
        <WayForward
          outcome={outcome}
          text={t("reset.done")}
          href="/login/"
          label={t("reset.login")}
          kind="main"
        />
      );
    // The check on its way: a status line; no answer, or the server's problem: why.
    if (!check.isSuccess)
      return check.isPending ? (
        <p role="status">{t("reset.checking")}</p>
      ) : (
        <ApiErrorAlert error={check.error} />
      );
    return theForm();
  }

  // Where each refusal shows: the form's own beside its box, the server's beside the new box, and
  // anything else in the alert (a key's refusal replaces the form, above). Called, not drawn as a
  // component of its own: one made inside this one would be new at every redraw, and React would
  // empty its boxes as the person types.
  function theForm() {
    const own = (code: string | undefined) => {
      if (!code) return undefined;
      return code === NOT_THE_SAME ? t("notTheSame") : codeMessage(words, code);
    };
    const server = fieldMessages(reset.error);
    const { errors } = form.formState;
    return (
      // noValidate: the browser's own checks would speak its language, not the shop's.
      <form
        noValidate
        onSubmit={(event) =>
          void form.handleSubmit((values) => reset.mutate(values))(event)
        }
        className="grid gap-6"
      >
        <Field
          label={t("new")}
          hint={t("newHint")}
          error={own(errors.fresh?.message) ?? server.password}
          type="password"
          // "new-password": the phone's password manager offers to make one, and saves it.
          autoComplete="new-password"
          {...form.register("fresh")}
          autoFocus
        />
        <Field
          label={t("again")}
          error={own(errors.again?.message)}
          type="password"
          autoComplete="new-password"
          {...form.register("again")}
        />
        {/* What no box can show: too many tries, no network. */}
        <ApiErrorAlert error={server.password ? null : reset.error} />
        <div>
          <Button type="submit" disabled={reset.isPending}>
            {t("save")}
          </Button>
        </div>
      </form>
    );
  }

  return (
    <div className="flex max-w-md flex-col gap-6">
      <h1 className="text-2xl font-semibold">{t("reset.title")}</h1>
      {whatShows()}
    </div>
  );
}

/** A sentence in place of the form, and the one way forward from it. */
function WayForward({
  outcome,
  text,
  href,
  label,
  kind = "second",
}: {
  /** Where focus goes as the sentence replaces the form. */
  outcome?: RefObject<HTMLParagraphElement | null>;
  text: string;
  href: string;
  label: string;
  kind?: "main" | "second";
}) {
  return (
    <>
      <p ref={outcome} tabIndex={-1} className="outline-none">
        {text}
      </p>
      <div>
        <ButtonLink href={href} kind={kind}>
          {label}
        </ButtonLink>
      </div>
    </>
  );
}
