// choose-password.tsx — Chagua nenosiri lako: a person on a temporary password chooses their own before
// the office opens (UI-5, AUTH-6, ADR-0038, 03 §5.9).
//
// The owner sets a first or forgotten password face to face, and tells it to the person (ADR-0038). Until
// they choose their own, every office route answers 403 password.must_change, and `me` says
// must_change_password (AUTH-4). So the office's frame shows this form in place of the screen
// (office-frame.tsx), and the person can still leave with Toka.
//
// The form sends the temporary password and the new one to allauth's change of one's own password, which
// always asks for the current one (AUTH-6). A 200 keeps this very session: `me` is asked again, says the
// mark is off, and the office opens, with no second login.
//
// What can go wrong, and where it shows:
//   a box left empty, or the new one typed differently twice   beside it, and nothing is sent
//   the temporary password wrong (enter_current_password)      beside its box
//   the new one refused: the temporary one, too short, too common, only numbers, too like the person
//                                                              beside the new box
//   too many tries (5 a minute), or no answer                  the alert
//
// "use client": it asks use-intl for words, and calls the server.
"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { useTranslations } from "use-intl";
import { z } from "zod";

import { callAllauth } from "@/api/allauth";
import { useApiErrorWords } from "@/api/errors";
import { ApiRefusal } from "@/api/refusal";
import { ApiErrorAlert } from "@/components/api-error-alert";
import { Button } from "@/components/design/button";
import { Field } from "@/components/design/field";
import { WHO_IS_HERE } from "@/features/people/who-is-here";
import { codeMessage, useCodeWords } from "@/i18n/codes";

import { NEW_PASSWORD, NOT_THE_SAME, TYPED_THE_SAME } from "./new-password";

// Only what the form can know: each box filled, and the new one typed the same twice (new-password.ts).
// Whether the temporary one is right, and the new one good enough, is the server's checker's to say.
const CHOOSE_FORM = z
  .object({
    temporary: z.string().min(1, { error: "required" }),
    ...NEW_PASSWORD,
  })
  .refine(...TYPED_THE_SAME);
type ChooseForm = z.infer<typeof CHOOSE_FORM>;

export function ChoosePassword() {
  const t = useTranslations("password");
  const words = useCodeWords();
  const { fieldMessages } = useApiErrorWords();
  const store = useQueryClient();

  const form = useForm<ChooseForm>({
    resolver: zodResolver(CHOOSE_FORM),
    defaultValues: { temporary: "", fresh: "", again: "" },
  });

  const choose = useMutation({
    mutationFn: ({ temporary, fresh }: ChooseForm) =>
      callAllauth({
        method: "POST",
        route: "account/password/change",
        // Not trimmed: sent as typed, as the login sends them.
        body: { current_password: temporary, new_password: fresh },
        // The session ended meanwhile, as when the owner set yet another temporary password.
        bare: { 401: "not_authenticated" },
      }),
    // The same person, the same session: nobody to forget. `me` is asked again, says the mark is off, and
    // the frame opens the screen in place of this form.
    onSuccess: () => store.invalidateQueries({ queryKey: WHO_IS_HERE }),
    // A refusal beside a box: the keyboard goes back to that box, to type again at once.
    onError: (error) => {
      const fields = error instanceof ApiRefusal ? error.body.fields : {};
      if (fields.current_password) form.setFocus("temporary");
      else if (fields.new_password) form.setFocus("fresh");
    },
  });

  // Where each refusal shows: the form's own beside its box, then the server's beside the box it names,
  // and anything else in the alert.
  const own = (code: string | undefined) => {
    if (!code) return undefined;
    return code === NOT_THE_SAME ? t("notTheSame") : codeMessage(words, code);
  };
  const server = fieldMessages(choose.error);
  const { errors } = form.formState;
  const onABox = Object.keys(server).length > 0;

  return (
    <div className="flex max-w-md flex-col gap-6">
      <h1 className="text-2xl font-semibold">{t("chooseTitle")}</h1>
      <p>{t("chooseIntro")}</p>
      {/* noValidate: the browser's own checks would speak its language, not the shop's. */}
      <form
        noValidate
        onSubmit={(event) =>
          void form.handleSubmit((values) => choose.mutate(values))(event)
        }
        className="grid gap-6"
      >
        <Field
          label={t("temporary")}
          error={own(errors.temporary?.message) ?? server.current_password}
          type="password"
          autoComplete="current-password"
          {...form.register("temporary")}
          // The person came straight from the login: the keyboard starts in the first box.
          autoFocus
        />
        <Field
          label={t("new")}
          hint={t("newHint")}
          error={own(errors.fresh?.message) ?? server.new_password}
          type="password"
          // "new-password": the phone's password manager offers to make one, and saves it.
          autoComplete="new-password"
          {...form.register("fresh")}
        />
        <Field
          label={t("again")}
          error={own(errors.again?.message)}
          type="password"
          autoComplete="new-password"
          {...form.register("again")}
        />
        {/* What no box can show: too many tries, no network, a session that ended. */}
        <ApiErrorAlert error={onABox ? null : choose.error} />
        <div>
          {/* Switched off while it is sent, and after it worked while `me` is asked again. */}
          <Button type="submit" disabled={choose.isPending || choose.isSuccess}>
            {t("save")}
          </Button>
        </div>
      </form>
    </div>
  );
}
