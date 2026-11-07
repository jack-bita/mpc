// api-error-alert.tsx — what went wrong with a call to the server, in the shop's words (UI-2, ADR-0040).
// An office screen puts it where the person will look, and hands it the error TanStack Query caught.
//
// Built on the alert piece's danger kind (UI-8): faded red, and role="alert", which a screen reader says
// at once, also when the box appears with its words already in it. So, unlike the offline banner, it
// needn't wait on the page empty: it can appear only when there is something to say.
"use client";

import { CircleAlert } from "lucide-react";
import { useTranslations } from "use-intl";

import { useApiErrorWords } from "@/api/errors";
import { Alert, AlertDescription, AlertTitle } from "@/components/design/alert";

/** Shows nothing while there is no error, so a screen can place it once and hand it `query.error`. */
export function ApiErrorAlert({ error }: { error: unknown }) {
  const t = useTranslations("apiError");
  const { message } = useApiErrorWords();
  if (error === null || error === undefined) return null;

  return (
    <Alert kind="danger">
      {/* The icon says what the title says, so a screen reader skips it. */}
      <CircleAlert aria-hidden="true" />
      <AlertTitle>{t("title")}</AlertTitle>
      <AlertDescription>{message(error)}</AlertDescription>
    </Alert>
  );
}
