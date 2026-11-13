// at-the-device.tsx — the home page of a registered device: the PIN login while nobody is logged in here,
// and who is, once someone is, under the shop's top bar (UI-4, 03 §5.9).
//
// Someone is here one of two ways:
//   by the server       `me` (useWhoIsHere) answers for the session this browser holds
//   by the laptop       an offline PIN check let them in, and their local session lasts (useOfflinePerson,
//                       offline-session.ts, SYNC-10); it comes first, as the server's session, if any, is
//                       being ended
// Either way: "Karibu, Asha", her name and the side she works on in the bar, all in her own language and
// font (UI-9), Toka and Badilisha mtu, and the idle lock. Mipangilio yangu only by the server: the office
// screens need its session.
//
// Nobody here, the PIN login shows, with its tiles from the laptop's own copy (SYNC-10):
//   `me` refused, under 500        nobody here, or a session the server ended, with why
//   no answer, or the server down   with the reason; the PIN is checked on the laptop
//   a logout not heard yet          its tiles come back once it can't reach the server, and the PIN is
//                                   checked on the laptop until it does (SYNC-10)
// A PIN login, a logout and a quick switch forget the last person, which asks `me` again
// (forgetTheLastPerson), so this follows each by itself. After the idle minutes untouched, the laptop logs
// the person out by itself (idle-lock.ts).
//
// The counter screens never ask the server who is here, so this page tells them: a note of whoever it shows,
// with the minutes their screen may sit untouched (at-the-counter.ts, SYNC-11). And it hears them: Toka on a
// counter screen hides the person there and asks this page, opened next, to log them out, as its own Toka
// does. The logout calls the server, so it stays here, outside the counter lock (UI-4's note).
//
// It calls the server, so it lives outside the counter lock (rule 5, ADR-0019).
//
// "use client": it asks the server and reads the device's saved copy, both in the browser only.
"use client";

import {
  useMutation,
  useMutationState,
  useQueryClient,
} from "@tanstack/react-query";
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
import { sideOfStaffRow } from "@/features/people/side-of-row";
import { sideAt, useWhoIsHere } from "@/features/people/who-is-here";
import { useRule, useSides, useStaff } from "@/offline/reference";
import { wholeNumber } from "@/offline/rules";

import {
  arriveAtCounter,
  type LeaveAsk,
  leaveHeard,
  nobodyAtCounter,
  useLeaveAsked,
} from "./at-the-counter";
import { useIdleLock } from "./idle-lock";
import {
  endOfflineSession,
  startOfflineSession,
  useOfflinePerson,
} from "./offline-session";
import { PinLogin } from "./pin-login";
import { UnsentNote } from "./unsent-note";
import type { StaffRow } from "./staff-picker";

/** What a logout is about: who pressed Toka or Badilisha mtu, or whom the idle lock logged out; and, for a
 * session the server refused, why, to say once. */
interface Leaving {
  by: string | null;
  notice: ApiRefusal | null;
}

/** Every logout's name in the store, so the screen sees each one still waiting, even one it let go of. */
const LOGOUT = ["auth", "logout"] as const;

/** The idle lock's minutes for someone logged in offline, if the laptop knows no rule: 03 §5.9's default.
 * Only a laptop never filled knows none, and its tiles wait for the first sync. */
const IDLE_MINUTES_UNKNOWN = 15;

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
  const attendance = useTranslations("attendance");
  const thisLaptop = useTranslations("thisLaptop");
  const me = useWhoIsHere();
  const store = useQueryClient();

  // Toka and Badilisha mtu: the session ends on the server first, then the store forgets the person,
  // which asks `me` again, for whoever is next. POST /api/auth/logout/ needs only the session and the
  // CSRF token, so it works on a blocked laptop and for a suspended person too (AUTH-4).
  const logout = useMutation<unknown, unknown, Leaving>({
    mutationKey: LOGOUT,
    mutationFn: () => answerOf(api.POST("/api/auth/logout/")),
    // Sent again while no answer comes, with no limit, until the server hears it. Offline, TanStack waits
    // for the network by itself, then sends it. Given up, the session would outlive the press: a network
    // back before its idle time ends it would bring the person back on the screen. A refusal the server
    // meant is never sent again: it would get the same no.
    retry: (_tries, error) => mayPassLater(error),
    onSuccess: () => forgetTheLastPerson(store),
  });
  // What the last logout was about, kept by the screen's hold on it: forgetTheLastPerson empties the
  // store's list of changes, but this hold keeps what it was sent with, and its error (UI-4's review).
  const leaver = logout.variables?.by ?? null;
  const notice = logout.variables?.notice ?? null;

  // Every logout not heard yet, read from the store, not from this screen's hold, which a tap on a tile
  // lets go of. While one waits, the server may still hold that session: the person stays hidden, and a
  // PIN is checked on the laptop, never sent: a login sent then would wait in the one queue of changes
  // behind the logout (CHANGES_IN_ORDER), for a network that may not come all day.
  const waiting = useMutationState({
    filters: { mutationKey: LOGOUT, status: "pending" },
    select: (mutation) => mutation.state,
  });
  const logoutWaits = waiting.length > 0;
  // One that can't reach the server for now: waiting for the network, or tried with no answer. Then the
  // tiles come back, and the next person logs in on the laptop's own check, rather than wait for a network
  // that may not come all day (SYNC-10). While one is still on its way with a hope of an answer, a moment
  // online, the screen says Unatoka…, and shows no tiles.
  const unheard = waiting.some(
    (state) => state.isPaused || state.failureCount > 0,
  );
  const leaving = logoutWaits && !unheard;

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
  // No answer from the server about who is here, and none before: no network (TanStack waits, paused), or
  // the server can't be reached or is broken. The PIN login then checks on the laptop (SYNC-10). From the
  // first try that got none (failureReason), not after the store's two more tries, three seconds later:
  // a laptop reloaded with no network shows its tiles at once.
  const noAnswer =
    !hasAnswer &&
    ended === null &&
    (me.fetchStatus === "paused" ||
      mayPassLater(me.error) ||
      mayPassLater(me.failureReason));
  const { mutate: sendLogout } = logout;
  useEffect(() => {
    // A reason: end that session on the server, and keep the reason with the logout, to say once.
    if (endedFor && !alreadySent) sendLogout({ by: null, notice: endedFor });
    // Ended by itself, at its idle time, with the person's last answer still in the store beside the
    // refusal: forget them at once. TanStack keeps that answer through every failed refresh after it, so a
    // 5xx or a dropped network would bring them back, with Toka and the idle lock (UI-4's review).
    else if (ended && !endedFor && hasAnswer) void forgetTheLastPerson(store);
  }, [endedFor, alreadySent, ended, hasAnswer, sendLogout, store]);

  // Whom a counter screen asked to log out, not heard yet (SYNC-11): hidden from the first drawing, as
  // the next person is already at the counter.
  const leaveAsked = useLeaveAsked();
  // Who is logged in. First, someone the laptop let in offline, whose local session still holds.
  const offlineRow = useOfflinePerson();
  const offlinePerson =
    offlineRow !== undefined && offlineRow.id === leaveAsked?.staffId
      ? undefined
      : offlineRow;
  // Else, as `me` last said. TanStack keeps the last answer through a failed refresh, so a dropped network
  // leaves the person where they are. Nobody while a logout of theirs waits: hidden at the press, here or
  // on a counter screen. offlineRow, not offlinePerson: one leaving still holds the laptop, and the
  // server's session from before them is being ended.
  const here =
    offlineRow ||
    ended ||
    logoutWaits ||
    (leaveAsked !== null && me.data?.staff.id === leaveAsked.staffId)
      ? undefined
      : me.data;
  const sides = useSides();
  const side = offlinePerson
    ? sideOfStaffRow(offlinePerson, device.homeSide.id, sides ?? [])
    : here
      ? sideAt(here, device.homeSide.id)
      : undefined;
  const person = offlinePerson
    ? { id: offlinePerson.id, name: offlinePerson.display_name }
    : here
      ? { id: here.staff.id, name: here.staff.display_name }
      : undefined;
  // Their own language and font: from `me`, or from their staff row for someone logged in offline. Nobody's
  // from the press of Toka, so the tiles come back in the laptop's own for whoever is next (UI-9).
  useFollowThePerson(offlinePerson ?? here?.user);
  // Focus on the welcome as each person arrives: the pad they typed on has gone, and focus with it.
  const welcome = useRef<HTMLHeadingElement>(null);
  useEffect(() => welcome.current?.focus(), [person?.id]);

  // The laptop's yes to a PIN typed offline: the person's local session starts at once. Whatever session
  // this browser holds on the server, from before the network went (a reload), is ended, sent again until
  // the server hears it: else, once the network is back, `me` would bring that person back after this
  // one's Toka. A logout already waiting does the same, so none is added then. Then the store forgets the
  // last person, as at every login; a logout on its way keeps its place (forgetTheLastPerson). In that
  // order, so a logout is in the store from the first moment: the forgetting waits for every screen's
  // read to be asked again, seconds with no network, and meanwhile `me` could answer with the old session.
  async function arrivedOffline(arrived: StaffRow) {
    startOfflineSession(arrived);
    const waitingNow = store
      .getMutationCache()
      .findAll({ mutationKey: LOGOUT, status: "pending" });
    if (waitingNow.length === 0) sendLogout({ by: null, notice: null });
    await forgetTheLastPerson(store);
  }

  // Toka, Badilisha mtu and the idle lock. Someone logged in offline: their local session ends, and the
  // server has nothing to hear, as their arrival already sent the logout. Else the logout names who leaves,
  // so a refused one's reason shows only while they are here.
  function leave() {
    if (offlinePerson) endOfflineSession();
    else logout.mutate({ by: here?.staff.id ?? null, notice: null });
  }

  // A seller who walks away is logged out by herself, as if she had pressed Toka. Only while someone is
  // here: while leaving, or with nobody, there is nothing to lock. Offline, the minutes are the shop's rule
  // as the laptop holds it, stored as text (SYNC-7), since there is no `me` to say them.
  const ruleMinutes = useRule("session.idle_minutes", null);
  // None, or 0, which would switch the lock off: the default, never a laptop left open.
  const ruleWhole = wholeNumber(ruleMinutes);
  const offlineMinutes =
    ruleWhole !== undefined && ruleWhole > 0 ? ruleWhole : IDLE_MINUTES_UNKNOWN;
  const idleMinutes = offlinePerson ? offlineMinutes : here?.idle_minutes;
  useIdleLock(idleMinutes, leave);

  // The counter's note (SYNC-11): whoever this page shows, by their row on the laptop, with the same
  // minutes as the lock above, so a counter screen locks as this page would. Nobody else: the note goes
  // as the person is hidden, at the press of Toka. Someone with no row on the laptop's copy, as before its
  // first sync, is nobody at the counter: it has no row to read them by.
  const staff = useStaff();
  const rowHere =
    offlinePerson ??
    (here ? staff?.find((row) => row.id === here.staff.id) : undefined);
  // How they came in, so a counter's Toka ends the right session: the local one, or the server's.
  const cameInBy = offlinePerson ? "laptop" : "server";
  useEffect(() => {
    if (rowHere !== undefined && idleMinutes !== undefined)
      arriveAtCounter(rowHere, idleMinutes, cameInBy);
    else nobodyAtCounter();
  }, [rowHere, idleMinutes, cameInBy]);

  // A counter screen asked to log someone out (SYNC-11). A ref, not state: the page may draw again before
  // the store shows the logout waiting, and that drawing must not send a second one.
  const leaveSentFor = useRef<LeaveAsk | null>(null);
  useEffect(() => {
    if (leaveAsked === null) {
      leaveSentFor.current = null;
      return;
    }
    // Someone the laptop let in: their local session ends here, if it still holds, and the server has
    // nothing to hear, as their arrival already sent the logout.
    if (leaveAsked.by === "laptop") {
      if (offlineRow?.id === leaveAsked.staffId) endOfflineSession();
      leaveHeard();
      return;
    }
    // A logout on its way, the one sent for this ask or one from before: it ends the one session this
    // browser holds, and hides the person from then on, as Toka here does. A second would add nothing.
    if (logoutWaits) {
      leaveHeard();
      return;
    }
    // Sent, its answer still to come: heard when it comes (onSettled, below), or once the store shows it
    // waiting (above).
    if (leaveSentFor.current === leaveAsked) return;
    // Her session is gone already: the server says nobody is here, or names someone else, or someone the
    // laptop let in has taken the counter, whose arrival sent the logout. A logout now would end theirs.
    const someoneElse =
      (me.data !== undefined && me.data.staff.id !== leaveAsked.staffId) ||
      offlineRow !== undefined;
    if (ended !== null || someoneElse) {
      leaveHeard();
      return;
    }
    // `me` still on its way, with no failure yet: it may name her, or someone else, whose session a logout
    // would end. Wait for it.
    if (me.data === undefined && !noAnswer) return;
    // Else the server's session gets its logout, as Toka here sends it: `me` names her, or can't answer at
    // all. After 5 minutes on a counter screen the store has forgotten `me`'s answer (TanStack's gcTime),
    // and with no network or a 5xx it can't ask again. Taken for nobody, the session would outlive the
    // press, and bring her back once the network returned. The logout waits, and is sent again until the
    // server hears it. Its answer is the ask's end: a refusal leaves her here with why, as Toka here does.
    leaveSentFor.current = leaveAsked;
    sendLogout(
      { by: leaveAsked.staffId, notice: null },
      { onSettled: () => leaveHeard() },
    );
  }, [
    leaveAsked,
    offlineRow,
    me.data,
    ended,
    noAnswer,
    logoutWaits,
    sendLogout,
  ]);

  // The status line's words: leaving, or asking `me` with nothing to show yet; else nothing. Not while it
  // waits for a network that isn't there, or asks again after no answer: the tiles say what to do then.
  const status = person
    ? null
    : leaving
      ? t("leaving")
      : me.isPending && me.fetchStatus === "fetching" && !noAnswer
        ? t("waiting")
        : null;

  function whatShows() {
    // While the logout is on its way: neither the person nor the tiles yet, only the status line below, a
    // moment online (UI-4's screens). A PIN login sent meanwhile would wait behind the logout anyway.
    if (person === undefined && leaving) return null;
    if (person)
      return (
        <>
          {/* A logout the server refused: why, and the person stays where they are. Only to them. */}
          {here && (
            <ApiErrorAlert
              error={leaver === here.staff.id ? logout.error : null}
            />
          )}
          <h1
            ref={welcome}
            tabIndex={-1}
            className="text-3xl font-semibold outline-none"
          >
            {t("welcome", { name: person.name })}
          </h1>
          <div className="flex flex-wrap gap-3">
            {/* The counter's first screen (SYNC-11): clocking in and out. Online or offline alike, as the
                counter needs no server; only for someone the counter's note names (rowHere), as a person
                the laptop has no row of would be sent straight back. Next's own link: the page moves with no
                reload, and the note, kept in this tab's memory, goes with her. */}
            {rowHere && (
              <ButtonLink href="/attendance/" size="normal">
                {attendance("title")}
              </ButtonLink>
            )}
            {/* Kompyuta hii (SYNC-12): whether the laptop keeps the shop's data, and the install. A counter
                screen, so the same rule as Mahudhurio: only for someone the counter's note names. */}
            {rowHere && (
              <ButtonLink href="/this-laptop/" kind="second" size="normal">
                {thisLaptop("title")}
              </ButtonLink>
            )}
            {/* The person's own language and font, one tap from the welcome: someone logged in by PIN
                never sees the office's home page (UI-9). Only by the server's session: its screen calls
                the server as that person, which a local session can't (SYNC-10). */}
            {here && (
              <ButtonLink href="/my-settings/" kind="second" size="normal">
                {settings("title")}
              </ButtonLink>
            )}
          </div>
        </>
      );
    // Plain "nobody is logged in" is no error to show: only a session that ended for a reason says why,
    // and only until the first tile is tapped, which forgets it for good, Rudi included. No answer at all:
    // the reason above the tiles, as the PIN is checked on the laptop.
    if (ended || noAnswer || unheard)
      return (
        <>
          {noAnswer && <ApiErrorAlert error={me.error} />}
          {/* Records still waiting to leave the laptop, after a Toka: safe here, sent by themselves (SYNC-12). */}
          <UnsentNote />
          <PinLogin
            notice={notice ?? undefined}
            onPick={() => logout.reset()}
            serverAway={noAnswer || logoutWaits}
            onOffline={arrivedOffline}
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
    // Nothing while `me` is on its way; the reason once it failed for another reason, a bug.
    return <ApiErrorAlert error={me.error} />;
  }

  // The bar's two buttons, only while someone is here. Both end the session the same way, and bring the
  // tiles back: Toka for someone leaving, Badilisha mtu for the next person stepping up (UI-4's plan).
  // The bar kind: the only kind that can sit on the green; normal height, as the language button's.
  const buttons = person ? (
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
      person={person?.name}
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
