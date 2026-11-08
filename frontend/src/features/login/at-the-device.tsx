// at-the-device.tsx — the home page of a registered device: the PIN login while nobody is logged in here,
// and who is, once someone is, under the shop's top bar (UI-4, 03 §5.9).
//
// It asks `me` (useWhoIsHere), which answers for the session this browser holds:
//   someone logged in             "Karibu, Asha", Mipangilio yangu, and her name and the side she works on
//                                 in the bar, all in her own language and font (UI-9)
//   refused, under 500            the PIN login: nobody here, or a session the server ended, with why
//   no answer, or the server down  the reason, and Inahitaji mtandao: the PIN login needs the network
// A PIN login, a logout and a quick switch forget the last person, which asks `me` again
// (forgetTheLastPerson), so this follows each by itself. After `me`'s idle minutes untouched, the laptop
// logs the person out by itself (idle-lock.ts).
//
// Until the counter screens come, someone logged in sees only the welcome and her settings' button (UI-4's
// plan, UI-9). It calls the server, so it lives outside the counter lock (rule 5, ADR-0019).
//
// "use client": it asks the server and reads the device's saved copy, both in the browser only.
"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { type ReactNode, useEffect, useRef } from "react";
import { useTranslations } from "use-intl";

import { api } from "@/api/client";
import { forgetTheLastPerson, mayPassLater } from "@/api/query-client";
import { answerOf, ApiRefusal } from "@/api/refusal";
import { ApiErrorAlert } from "@/components/api-error-alert";
import { AppFrame } from "@/components/app-frame";
import { Button, ButtonLink } from "@/components/design/button";
import { OfflineBanner } from "@/components/offline-banner";
import type { ThisDevice } from "@/features/devices/this-device";
import { useFollowThePerson } from "@/features/people/follow-the-person";
import { sideAt, useWhoIsHere } from "@/features/people/who-is-here";

import { useIdleLock } from "./idle-lock";
import { PinLogin } from "./pin-login";

/** What a logout is about: who pressed Toka or Badilisha mtu, or whom the idle lock logged out; and, for a
 * session the server refused, why, to say once. */
interface Leaving {
  by: string | null;
  notice: ApiRefusal | null;
}

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
  const settings = useTranslations("mySettings");
  const me = useWhoIsHere();
  const store = useQueryClient();

  // Toka and Badilisha mtu: the session ends on the server first, then the store forgets the person,
  // which asks `me` again, for whoever is next. POST /api/auth/logout/ needs only the session and the
  // CSRF token, so it works on a blocked laptop and for a suspended person too (AUTH-4).
  const logout = useMutation<unknown, unknown, Leaving>({
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
  // What the last logout was about, kept by the screen's hold on it: forgetTheLastPerson empties the
  // store's list of changes, but this hold keeps what it was sent with, and its error (UI-4's review).
  const leaver = logout.variables?.by ?? null;
  const notice = logout.variables?.notice ?? null;

  // The server refused this browser's session: nobody is logged in here, or a session ended, as when the
  // person was suspended or a new PIN was set. Under 500 only: a 5xx is the server broken, and says
  // nothing about who is here.
  const ended =
    me.error instanceof ApiRefusal && me.error.status < 500 ? me.error : null;
  // Ended for a reason, as a suspension or a new PIN: the server refuses that session with the same
  // reason at every visit until its idle time, so the next person at the counter would be told it.
  const endedFor =
    ended && ended.body.code !== "not_authenticated" ? ended : null;
  // This very refusal went with the last logout: never sent again for it, even if the server refused that
  // logout, or the screen would send one after another.
  const alreadySent =
    endedFor !== null && logout.variables?.notice === endedFor;
  const hasAnswer = me.data !== undefined;
  const { mutate: sendLogout } = logout;
  useEffect(() => {
    // A reason: end that session on the server, and keep the reason with the logout, to say once.
    if (endedFor && !alreadySent) sendLogout({ by: null, notice: endedFor });
    // Ended by itself, at its idle time, with the person's last answer still in the store beside the
    // refusal: forget them at once. TanStack keeps that answer through every failed refresh after it, so a
    // 5xx or a dropped network would bring them back, with Toka and the idle lock (UI-4's review).
    else if (ended && !endedFor && hasAnswer) void forgetTheLastPerson(store);
  }, [endedFor, alreadySent, ended, hasAnswer, sendLogout, store]);
  // Who is logged in, as `me` last said. TanStack keeps the last answer through a failed refresh, so a
  // dropped network leaves the person where they are. Nobody while they are leaving: hidden at the press.
  const here = ended || leaving ? undefined : me.data;
  const side = here ? sideAt(here, device.homeSide.id) : undefined;
  // Their own language and font, from that same `here`: nobody's from the press of Toka, so the tiles come
  // back in the laptop's own for whoever is next (UI-9).
  useFollowThePerson(here);
  // Focus on the welcome as each person arrives: the pad they typed on has gone, and focus with it.
  const welcome = useRef<HTMLHeadingElement>(null);
  const hereId = here?.staff.id;
  useEffect(() => welcome.current?.focus(), [hereId]);

  // Toka, Badilisha mtu and the idle lock: the logout names who leaves, so a refused one's reason shows
  // only while they are here.
  function leave() {
    logout.mutate({ by: here?.staff.id ?? null, notice: null });
  }

  // A seller who walks away is logged out by herself, as if she had pressed Toka. Only while someone is
  // here: while leaving, or with nobody, there is nothing to lock.
  useIdleLock(here?.idle_minutes, leave);

  // The status line's words: leaving, or waiting for `me` with nothing to show yet; else nothing.
  const status = leaving ? t("leaving") : me.isPending ? t("waiting") : null;

  function whatShows() {
    // While the logout is on its way: neither the person nor the tiles yet, only the status line below. A
    // PIN login sent meanwhile could be ended by her logout, if it landed after his login.
    if (leaving) return null;
    if (here)
      return (
        <>
          {/* A logout the server refused: why, and the person stays where they are. Only to them. */}
          <ApiErrorAlert
            error={leaver === here.staff.id ? logout.error : null}
          />
          <h1
            ref={welcome}
            tabIndex={-1}
            className="text-3xl font-semibold outline-none"
          >
            {t("welcome", { name: here.staff.display_name })}
          </h1>
          {/* The person's own language and font, one tap from the welcome: someone logged in by PIN
              never sees the office's home page (UI-9). */}
          <div>
            <ButtonLink href="/my-settings/" kind="second" size="normal">
              {settings("title")}
            </ButtonLink>
          </div>
        </>
      );
    // Plain "nobody is logged in" is no error to show: only a session that ended for a reason says why,
    // and only until the first tile is tapped, which forgets it for good, Rudi included.
    if (ended)
      return (
        <>
          <PinLogin
            notice={notice ?? undefined}
            onPick={() => logout.reset()}
          />
          {/* The way in for someone with a password and no PIN, as the owner may be: the password login
              (/login/). The second kind, under the tiles, which are what the counter is for (Jack,
              8 Nov 2026, at UI-5's review). A seller who taps it still needs a password. */}
          <div>
            <ButtonLink href="/login/" kind="second" size="normal">
              {t("withPassword")}
            </ButtonLink>
          </div>
        </>
      );
    // Nothing while `me` is on its way; the reason once it failed with no answer at all.
    return <ApiErrorAlert error={me.error} />;
  }

  // The bar's two buttons, only while someone is here. Both end the session the same way, and bring the
  // tiles back: Toka for someone leaving, Badilisha mtu for the next person stepping up (UI-4's plan).
  // The bar kind: the only kind that can sit on the green; normal height, as the language button's.
  const buttons = here ? (
    <>
      <Button kind="bar" size="normal" onClick={leave}>
        {t("switch")}
      </Button>
      <Button kind="bar" size="normal" onClick={leave}>
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
      {/* role="status": a screen reader says its words as they change. Always on the page, empty and hidden
          from the eye (sr-only) while there is nothing to say: a status line that comes with its words in it
          often goes unsaid (NVDA, JAWS), as the offline banner's comment says (UI-4's review). It says the
          laptop is logging out, or to wait while it asks who is here, as it opens and after each login. */}
      <p role="status" className={status ? "text-lg" : "sr-only"}>
        {status}
      </p>
      {whatShows()}
      {children}
    </AppFrame>
  );
}
