// password-login.tsx — Ingia: the owner and managers log in on their own phones, by phone or email and a
// password (UI-5, ADR-0038, 03 §5.9).
//
// One box takes the phone or the email (login-name.ts), one the password. allauth's login checks them and
// starts the same Django session the office screens read. Then the store of server answers forgets
// whoever was here before (forgetTheLastPerson), and the person goes on to the office.
//
// What can go wrong, and where it shows:
//   a box left empty                                   beside it, and nothing is sent
//   a wrong password, a phone that is no real number   beside the box allauth names
//   this browser holds a session already (409)         the alert: log out first; and `me`, asked
//                                                      again, says whose, with Toka (below)
//   the right password, for someone switched off (401)  the alert: talk to the owner
//   too many tries (allauth's count, or a 429)         the alert: wait a little
//   no answer at all                                   the alert: check the internet
//
// `me` says whether a session already holds this browser, and the page acts on it:
//   the person's own password login       straight on to the office, with no form
//   someone's PIN login, at a laptop       their name, and Toka: a login would meet their session (409),
//                                           and after a reset on that laptop Ingia went into it (UI-5's review)
//   a session refused for a reason          why, and Toka, as the office says it (office-frame.tsx)
// Toka ends that session on the server, sent again until it is heard, and the store forgets the person;
// the form shows then. A login answered 409 asks `me` again, to learn whose session it met.
//
// Its page, /login/, is outside the counter's lock (rule 5): logging in calls the server.
//
// "use client": it asks use-intl for words, and calls the server.
"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { useTranslations } from "use-intl";
import { z } from "zod";

import { callAllauth } from "@/api/allauth";
import { api } from "@/api/client";
import { useApiErrorWords } from "@/api/errors";
import { forgetTheLastPerson, mayPassLater } from "@/api/query-client";
import { answerOf, ApiRefusal } from "@/api/refusal";
import { ApiErrorAlert } from "@/components/api-error-alert";
import { Button, ButtonLink } from "@/components/design/button";
import { Field } from "@/components/design/field";
import { PasswordField } from "@/components/design/password-field";
import { useWhoIsHere, WHO_IS_HERE } from "@/features/people/who-is-here";
import { codeMessage, useCodeWords } from "@/i18n/codes";

import { loginName } from "./login-name";

/** Where a person goes once logged in: the office's home page, with a button for each screen they may
 * open (office-home.tsx). */
export const AFTER_LOGIN = "/office/";

// The form's own rules, checked before anything is sent. Each names what is wrong by a code, as the
// server does, so its sentence comes from the same book ("required": Jaza sehemu hii). Only "not empty":
// whether a phone is a real number, or a password the right one, is the server's to say.
const LOGIN_FORM = z.object({
  // Spaces alone are nothing typed. A phone's own spaces come off in loginName().
  name: z.string().trim().min(1, { error: "required" }),
  // Not trimmed: the password goes as typed, and allauth takes spaces off its ends itself (03 §5.9).
  password: z.string().min(1, { error: "required" }),
});
type LoginForm = z.infer<typeof LOGIN_FORM>;

export function PasswordLogin() {
  const t = useTranslations("login.password");
  // The PIN login's book, for its "Subiri kidogo…", which this page says the same way.
  const loginWords = useTranslations("login");
  const words = useCodeWords();
  const { fieldMessages } = useApiErrorWords();
  const store = useQueryClient();
  const router = useRouter();
  const me = useWhoIsHere();

  const form = useForm<LoginForm>({
    resolver: zodResolver(LOGIN_FORM),
    defaultValues: { name: "", password: "" },
  });

  const login = useMutation({
    mutationFn: ({ name, password }: LoginForm) =>
      callAllauth({
        method: "POST",
        route: "auth/login",
        body: { ...loginName(name), password },
        // allauth's two answers with no code of their own (AUTH-3, AUTH-4).
        bare: { 401: "login.switched_off", 409: "login.already_in" },
      }),
    // What it was sent with holds the password: dropped from the store the moment nothing shows it,
    // not kept TanStack's 5 minutes after a wrong try, on a laptop the next person uses (UI-5's review).
    gcTime: 0,
    onSuccess: async () => {
      // A phone may be lent and a laptop is shared: the next person must never see the last one's
      // answers (UI-4). No change can be waiting to be sent: this page sends none but the login.
      await forgetTheLastPerson(store);
      // replace, not push: Back from the office shouldn't open the login again.
      router.replace(AFTER_LOGIN);
    },
    onError: (error) => {
      // A session holds this browser after all, as one made in another tab after this page opened: `me`
      // is asked again, to say whose, and the page offers Toka.
      if (error instanceof ApiRefusal && error.status === 409)
        void store.invalidateQueries({ queryKey: WHO_IS_HERE });
      // A refusal beside a box: the keyboard goes back to that box, to type again at once.
      const fields = error instanceof ApiRefusal ? error.body.fields : {};
      if (fields.password) form.setFocus("password");
      else if (fields.email ?? fields.phone) form.setFocus("name");
    },
  });

  // Toka, for a session that holds this browser: it ends on the server first, then the store forgets
  // the person, which asks `me` again, and the form shows. Needs only the session and the CSRF token, so
  // it works for a suspended person too (AUTH-4).
  const logout = useMutation({
    mutationFn: () => answerOf(api.POST("/api/auth/logout/")),
    // Sent again while no answer comes, until the server hears it, as every Toka is (office-frame.tsx).
    retry: (_tries, error) => mayPassLater(error),
    onSuccess: () => forgetTheLastPerson(store),
  });
  const leaving = logout.isPending;

  // Only an answer asked since this page opened, and not refused since: the store may still hold the
  // last person's answer, from a session that has ended since, and the office would send them straight
  // back here (office-frame.tsx).
  const fresh = me.isSuccess && me.isFetchedAfterMount ? me.data : undefined;
  // The person's own password login: straight on, as a login would send them. A password's `me` names
  // no device (AUTH-4).
  const here = fresh !== undefined && fresh.device === null;
  // Someone's PIN login at this laptop: theirs, not the person's at the keyboard.
  const someoneElse =
    fresh !== undefined && fresh.device !== null ? fresh : null;
  // A session refused for a reason, as a suspension: it still stands, and a login would meet it. Plain
  // "nobody is here" is no reason, and a 5xx says nothing about who is here.
  const refusedFor =
    me.error instanceof ApiRefusal &&
    me.error.status < 500 &&
    me.error.body.code !== "not_authenticated"
      ? me.error
      : null;
  useEffect(() => {
    if (here) router.replace(AFTER_LOGIN);
  }, [here, router]);

  // Where each refusal shows: the form's own beside its box, then the server's beside the box it names
  // (allauth calls the first box email or phone, by what was sent), and anything else in the alert.
  const own = (code: string | undefined) =>
    code ? codeMessage(words, code) : undefined;
  const server = fieldMessages(login.error);
  const nameError =
    own(form.formState.errors.name?.message) ?? server.email ?? server.phone;
  const passwordError =
    own(form.formState.errors.password?.message) ?? server.password;
  // Only the boxes on show: a refusal naming a box this form hasn't got (allauth's username, say) would
  // otherwise hide the alert, and say itself nowhere.
  const onABox = Boolean(server.email ?? server.phone ?? server.password);

  // Until `me` first answers, and while someone already here is sent on: no form, only "Subiri
  // kidogo…". Shown at once, the form flashed for a moment before the office opened (UI-5's hand test).
  // A first failure ends the wait: offline, `me` is asked again a few times, and the form needn't wait.
  const waiting = (me.isPending && me.failureCount === 0) || here || leaving;

  return (
    <div className="flex max-w-md flex-col gap-6">
      <h1 className="text-2xl font-semibold">{t("title")}</h1>
      {/* role="status": a screen reader says its words as they change. Always on the page, empty and
          hidden from the eye while there is nothing to say, as one that comes with its words in it often
          goes unsaid (offline-banner.tsx). */}
      <p role="status" className={waiting ? "text-lg" : "sr-only"}>
        {leaving
          ? loginWords("leaving")
          : waiting
            ? loginWords("waiting")
            : null}
      </p>
      {waiting ? null : someoneElse || refusedFor ? aSessionHolds() : theForm()}
    </div>
  );

  // A session holds this browser: whose, or why it was refused, and Toka to end it. A refused logout says
  // why under it, and the session stays.
  function aSessionHolds() {
    return (
      <div className="grid gap-4">
        {someoneElse ? (
          <p>{t("someoneHere", { name: someoneElse.staff.display_name })}</p>
        ) : (
          <ApiErrorAlert error={refusedFor} />
        )}
        <div>
          <Button onClick={() => logout.mutate()}>
            {loginWords("logout")}
          </Button>
        </div>
        <ApiErrorAlert error={logout.error} />
      </div>
    );
  }

  // The form and the way back in. Called, not drawn as a component of its own: one made inside this one
  // would be new at every redraw, and React would empty its boxes as the person types.
  function theForm() {
    return (
      <>
        {/* noValidate: the browser's own checks would speak its language, not the shop's. */}
        <form
          noValidate
          onSubmit={(event) =>
            void form.handleSubmit((values) => login.mutate(values))(event)
          }
          className="grid gap-6"
        >
          <Field
            label={t("name")}
            hint={t("nameHint")}
            error={nameError}
            {...form.register("name")}
            // The person came here to log in: the keyboard starts in the first box.
            autoFocus
            // "username": the phone's password manager fills the box it saved, a phone or an email.
            autoComplete="username"
            autoCapitalize="none"
            autoCorrect="off"
            spellCheck={false}
          />
          <PasswordField
            label={t("password")}
            error={passwordError}
            autoComplete="current-password"
            {...form.register("password")}
          />
          {/* What no box can show: log out first, switched off, too many tries, no network. */}
          <ApiErrorAlert error={onABox ? null : login.error} />
          <div>
            {/* Switched off while it is sent, and after it worked while the office opens: a second tap
              would meet the session the first one started, and get a 409. The boxes stay on, so a
              refusal can put the keyboard back in its box. */}
            <Button type="submit" disabled={login.isPending || login.isSuccess}>
              {t("send")}
            </Button>
          </div>
        </form>
        {/* Both ways back in: the owner face to face, or an email link (forgot-password.tsx). The second
          kind, as it leads away from the form's one action. */}
        <div>
          <ButtonLink href="/forgot-password/" kind="second" size="normal">
            {t("forgot")}
          </ButtonLink>
        </div>
      </>
    );
  }
}
