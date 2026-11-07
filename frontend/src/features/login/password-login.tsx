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
//   this browser holds a session already (409)         the alert: log out first
//   the right password, for someone switched off (401)  the alert: talk to the owner
//   too many tries (allauth's count, or a 429)         the alert: wait a little
//   no answer at all                                   the alert: check the internet
//
// Someone already logged in on this phone, whom `me` answers for, goes straight on, with no form.
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
import { useApiErrorWords } from "@/api/errors";
import { forgetTheLastPerson } from "@/api/query-client";
import { ApiRefusal } from "@/api/refusal";
import { ApiErrorAlert } from "@/components/api-error-alert";
import { Button } from "@/components/design/button";
import { Field } from "@/components/design/field";
import { useWhoIsHere } from "@/features/people/who-is-here";
import { codeMessage, useCodeWords } from "@/i18n/codes";

import { loginName } from "./login-name";

/** Where a person goes once logged in. */
export const AFTER_LOGIN = "/devices/";

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
    onSuccess: async () => {
      // A phone may be lent and a laptop is shared: the next person must never see the last one's
      // answers (UI-4). No change can be waiting to be sent: this page sends none but the login.
      await forgetTheLastPerson(store);
      // replace, not push: Back from the office shouldn't open the login again.
      router.replace(AFTER_LOGIN);
    },
    // A refusal beside a box: the keyboard goes back to that box, to type again at once.
    onError: (error) => {
      const fields = error instanceof ApiRefusal ? error.body.fields : {};
      if (fields.password) form.setFocus("password");
      else if (fields.email ?? fields.phone) form.setFocus("name");
    },
  });

  // Already logged in on this phone: straight on, as a login would send them. `me` refuses everyone
  // else, which is no error to show here.
  const here = me.data !== undefined;
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
  const onABox = Object.keys(server).length > 0;

  return (
    <div className="flex max-w-md flex-col gap-6">
      <h1 className="text-2xl font-semibold">{t("title")}</h1>
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
        <Field
          label={t("password")}
          error={passwordError}
          type="password"
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
    </div>
  );
}
