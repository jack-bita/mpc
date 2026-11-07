// at-the-device.tsx — the home page of a registered device: the PIN login while nobody is logged in here,
// and who is, once someone is, under the shop's top bar (UI-4, 03 §5.9).
//
// It asks `me` (useWhoIsHere), which answers for the session this browser holds:
//   someone logged in             "Karibu, Asha", and her name and the side she works on in the bar
//   refused, under 500            the PIN login: nobody here, or a session the server ended, with why
//   no answer, or the server down  the reason, and Inahitaji mtandao: the PIN login needs the network
// A PIN login, a logout and a quick switch forget the last person, which asks `me` again
// (forgetTheLastPerson), so this follows each by itself.
//
// Until the counter screens come, someone logged in sees only the welcome (UI-4's plan). It calls the
// server, so it lives outside the counter lock (rule 5, ADR-0019).
//
// "use client": it asks the server and reads the device's saved copy, both in the browser only.
"use client";

import type { ReactNode } from "react";
import { useTranslations } from "use-intl";

import { ApiRefusal } from "@/api/refusal";
import { ApiErrorAlert } from "@/components/api-error-alert";
import { AppFrame } from "@/components/app-frame";
import { OfflineBanner } from "@/components/offline-banner";
import type { ThisDevice } from "@/features/devices/this-device";
import { sideAt, useWhoIsHere } from "@/features/people/who-is-here";

import { PinLogin } from "./pin-login";

export function AtTheDevice({
  device,
  children,
}: {
  /** This device, as its saved copy knows it: the bar's shop, and the home side a person's side is
   * compared with. */
  device: ThisDevice;
  /** What the home page shows under every step, like the app's version. */
  children?: ReactNode;
}) {
  const t = useTranslations("login");
  const me = useWhoIsHere();

  // The server refused this browser's session: nobody is logged in here, or a session ended, as when the
  // person was suspended or a new PIN was set. Under 500 only: a 5xx is the server broken, and says
  // nothing about who is here.
  const ended =
    me.error instanceof ApiRefusal && me.error.status < 500 ? me.error : null;
  // Who is logged in, as `me` last said. TanStack keeps the last answer through a failed refresh, so a
  // dropped network leaves the person where they are.
  const here = ended ? undefined : me.data;
  const side = here ? sideAt(here, device.homeSide.id) : undefined;

  function whatShows() {
    if (here)
      return (
        <h1 className="text-3xl font-semibold">
          {t("welcome", { name: here.staff.display_name })}
        </h1>
      );
    // Plain "nobody is logged in" is no error to show: only a session that ended for a reason says why.
    if (ended)
      return (
        <PinLogin
          notice={ended.body.code === "not_authenticated" ? undefined : ended}
        />
      );
    // Nothing while `me` is on its way; the reason once it failed with no answer at all.
    return <ApiErrorAlert error={me.error} />;
  }

  return (
    <AppFrame
      area="login"
      notice={<OfflineBanner />}
      person={here?.staff.display_name}
      side={side ? { name: side.name } : undefined}
    >
      {whatShows()}
      {children}
    </AppFrame>
  );
}
