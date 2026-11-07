// at-the-device.tsx — the home page of a registered device: the PIN login while nobody is logged in here,
// and who is, once someone is, under the shop's top bar (UI-4, 03 §5.9).
//
// It asks `me` (useWhoIsHere), which answers for the session this browser holds:
//   someone logged in             "Karibu, Asha", and her name and the side she works on in the bar
//   refused, under 500            the PIN login: nobody here, or a session the server ended, with why
//   no answer, or the server down  the reason, and Inahitaji mtandao: the PIN login needs the network
// A PIN login, a logout and a quick switch forget the last person, which asks `me` again
// (forgetTheLastPerson), so this follows each by itself. After `me`'s idle minutes untouched, the laptop
// logs the person out by itself (idle-lock.ts).
//
// Until the counter screens come, someone logged in sees only the welcome (UI-4's plan). It calls the
// server, so it lives outside the counter lock (rule 5, ADR-0019).
//
// "use client": it asks the server and reads the device's saved copy, both in the browser only.
"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { type ReactNode, useEffect } from "react";
import { useTranslations } from "use-intl";

import { api } from "@/api/client";
import { forgetTheLastPerson, mayPassLater } from "@/api/query-client";
import { answerOf, ApiRefusal } from "@/api/refusal";
import { ApiErrorAlert } from "@/components/api-error-alert";
import { AppFrame } from "@/components/app-frame";
import { Button } from "@/components/design/button";
import { OfflineBanner } from "@/components/offline-banner";
import type { ThisDevice } from "@/features/devices/this-device";
import { sideAt, useWhoIsHere } from "@/features/people/who-is-here";

import { useIdleLock } from "./idle-lock";
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
  const store = useQueryClient();

  // Toka and Badilisha mtu: the session ends on the server first, then the store forgets the person,
  // which asks `me` again, for whoever is next. POST /api/auth/logout/ needs only the session and the
  // CSRF token, so it works on a blocked laptop and for a suspended person too (AUTH-4).
  const logout = useMutation({
    mutationFn: () => answerOf(api.POST("/api/auth/logout/")),
    // Sent again while no answer comes, with no limit, until the server hears it. Offline, TanStack waits
    // for the network by itself, then sends it. Given up, the session would outlive the press: a network
    // back before its idle time ends it would bring the person back on the screen. A refusal the server
    // meant is never sent again: it would get the same no.
    retry: (_tries, error) => mayPassLater(error),
    onSuccess: () => forgetTheLastPerson(store),
  });
  // True from the press until the server has heard, offline too: the person is hidden meanwhile.
  const leaving = logout.isPending;

  // The server refused this browser's session: nobody is logged in here, or a session ended, as when the
  // person was suspended or a new PIN was set. Under 500 only: a 5xx is the server broken, and says
  // nothing about who is here.
  const ended =
    me.error instanceof ApiRefusal && me.error.status < 500 ? me.error : null;
  // The server ended a session it had shown, and the person's last answer is still in the store beside
  // the refusal. Forget them at once: TanStack keeps that answer through every failed refresh after it,
  // so a 5xx or a dropped network would bring them back, with Toka and the idle lock (UI-4's review).
  const endedWithAnAnswer = ended !== null && me.data !== undefined;
  useEffect(() => {
    if (endedWithAnAnswer) void forgetTheLastPerson(store);
  }, [endedWithAnAnswer, store]);
  // Who is logged in, as `me` last said. TanStack keeps the last answer through a failed refresh, so a
  // dropped network leaves the person where they are. Nobody while they are leaving: hidden at the press.
  const here = ended || leaving ? undefined : me.data;
  const side = here ? sideAt(here, device.homeSide.id) : undefined;
  // A seller who walks away is logged out by herself, as if she had pressed Toka. Only while someone is
  // here: while leaving, or with nobody, there is nothing to lock.
  useIdleLock(here?.idle_minutes, () => logout.mutate());

  function whatShows() {
    // While the logout is on its way: neither the person nor the tiles yet. A PIN login sent meanwhile
    // could be ended by her logout, if it landed after his login.
    if (leaving)
      return (
        // role="status": a screen reader says it, as the screen empties.
        <p role="status" className="text-lg">
          {t("leaving")}
        </p>
      );
    if (here)
      return (
        <>
          {/* A logout the server refused: why, and the person stays where they are. */}
          <ApiErrorAlert error={logout.error} />
          <h1 className="text-3xl font-semibold">
            {t("welcome", { name: here.staff.display_name })}
          </h1>
        </>
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

  // The bar's two buttons, only while someone is here. Both end the session the same way, and bring the
  // tiles back: Toka for someone leaving, Badilisha mtu for the next person stepping up (UI-4's plan).
  // The bar kind: the only kind that can sit on the green; normal height, as the language button's.
  const buttons = here ? (
    <>
      <Button kind="bar" size="normal" onClick={() => logout.mutate()}>
        {t("switch")}
      </Button>
      <Button kind="bar" size="normal" onClick={() => logout.mutate()}>
        {t("logout")}
      </Button>
    </>
  ) : undefined;

  return (
    <AppFrame
      area="login"
      notice={<OfflineBanner />}
      person={here?.staff.display_name}
      side={side ? { name: side.name } : undefined}
      actions={buttons}
    >
      {whatShows()}
      {children}
    </AppFrame>
  );
}
