// password-reset.tsx — Weka nenosiri jipya: the page an email's reset link opens, at
// /password-reset/#<key> (UI-5, AUTH-3, ADR-0038, 03 §5.9).
//
// The key sits after the #, which a browser never sends to a server, so no log ever holds it
// (HEADLESS_FRONTEND_URLS, backend/config/settings/base.py). The page reads it from the address, then
// takes it out of the address bar and the tab's own entry at once, every time a link brings it, and
// Next.js's router forgets it too: the key sets the person's password for the hour it works, and the next
// person at this tab must not find it there, nor by Back.
//
// Honest limit: the browser's own list of pages visited, and its suggestions as an address is typed,
// keep the link as it was opened, key and all. No page can reach those. The key still works only once,
// for an hour, and a new password ends it (AUTH-3); on a shared laptop, use a private window.
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
import { PasswordField } from "@/components/design/password-field";
import { codeMessage, useCodeWords } from "@/i18n/codes";

import { NEW_PASSWORD, NOT_THE_SAME, TYPED_THE_SAME } from "./new-password";

const RESET_FORM = z.object(NEW_PASSWORD).refine(...TYPED_THE_SAME);
type ResetForm = z.infer<typeof RESET_FORM>;

// What follows the # in the address. As it is, never decoded: allauth's keys are letters, digits and
// dashes, and a broken escape would throw (client.ts reads its cookie the same way).
function addressKey(): string {
  return window.location.hash.slice(1);
}

// Said by the page itself once it has taken the key out: replaceState fires no event, so without it the
// page would go on reading the old address, and the same link pasted again would look like no change.
const KEY_TAKEN_OUT = "mpc:reset-key-taken-out";

// A link pasted into the same tab changes only what follows the #: the page follows it, and its own
// taking out of the key.
function onNewKey(listener: () => void): () => void {
  window.addEventListener("hashchange", listener);
  window.addEventListener(KEY_TAKEN_OUT, listener);
  return () => {
    window.removeEventListener("hashchange", listener);
    window.removeEventListener(KEY_TAKEN_OUT, listener);
  };
}

/** The key the link brought: undefined while the page is built (no address exists then), null when the
 * link held none. Each time the address holds one, it is taken out of the address bar and the tab's entry,
 * and the page keeps its own copy. */
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
    // Every time the address holds a key: the same link pasted twice changes nothing the page keeps, and
    // would leave the key in the address bar (UI-5's review).
    if (!inTheAddress) return;
    // replaceState, not a new entry: Back must not bring the key back either. null, not history.state:
    // Next.js patches replaceState, and a call carrying its own state (__NA) is taken for its own, so its
    // router would keep the old address, key and all, and write it back at its next change. Given null,
    // it copies its state into the entry itself and takes the new address
    // (next/dist/client/components/app-router.js).
    window.history.replaceState(
      null,
      "",
      window.location.pathname + window.location.search,
    );
    window.dispatchEvent(new Event(KEY_TAKEN_OUT));
  }, [inTheAddress, kept]);
  if (kept) return kept;
  return inTheAddress === undefined ? undefined : null;
}

/** Whether a refusal is about the link's key: used once already, or older than an hour. */
function aboutTheKey(error: unknown): boolean {
  return error instanceof ApiRefusal && error.body.fields.key !== undefined;
}

export function PasswordReset() {
  const t = useTranslations("password");
  const key = useTheLinksKey();

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
    // Drawn afresh for each key (React's `key`): a new link pasted into the same tab changes only what
    // follows the #, so the browser doesn't reload the page, and the old link's check, form and answer
    // would stay on show (UI-5's hand test).
    return <WithTheKey key={key} linkKey={key} />;
  }

  return (
    <div className="flex max-w-md flex-col gap-6">
      <h1 className="text-2xl font-semibold">{t("reset.title")}</h1>
      {whatShows()}
    </div>
  );
}

/** One link's key: its check, the form, and the answer. */
function WithTheKey({ linkKey }: { linkKey: string }) {
  const t = useTranslations("password");
  const words = useCodeWords();
  const { fieldMessages } = useApiErrorWords();

  // Asked once for each key: a key stays good or dead, and its answer isn't worth keeping once the page
  // is gone. The key is in the answer's name, so one link's answer never stands in for another's.
  const check = useQuery({
    queryKey: ["auth", "password-reset", linkKey],
    queryFn: () =>
      callAllauth({
        method: "GET",
        route: "auth/password/reset",
        headers: { "X-Password-Reset-Key": linkKey },
      }),
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
        body: { key: linkKey, password: fresh },
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

  // Where each refusal shows: the form's own beside its box, the server's beside the new box, and
  // anything else in the alert (a key's refusal replaces the form, above).
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
      <PasswordField
        label={t("new")}
        hint={t("newHint")}
        error={own(errors.fresh?.message) ?? server.password}
        // "new-password": the phone's password manager offers to make one, and saves it.
        autoComplete="new-password"
        {...form.register("fresh")}
        autoFocus
      />
      <PasswordField
        label={t("again")}
        error={own(errors.again?.message)}
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
