// pin-login.tsx — logging in by PIN at a shop's shared device, in two steps: "Wewe ni nani?" with a tile
// for each person (staff-picker.tsx), then the pad under the person's name (pin-pad.tsx) (UI-4, 03 §5.9).
//
// The 4th digit sends who and the PIN to POST /api/auth/pin-login/, with the device's key in its cookie.
// A yes starts a session for that person on this device and answers 204 with nothing: the store then
// forgets the last person (forgetTheLastPerson), which asks `me` again, and the home page shows who is
// here (UI-4). The laptop also saves its own check of that PIN, for a login with no network later
// (rememberPin, SYNC-10). A no shows the server's reason above the pad, which is ready for the next try: a
// wrong PIN, a lock with its minutes, a suspension.
//
// With no network, the laptop checks the PIN itself (checkPinOffline, SYNC-10), and its yes hands the
// person to the home page, which starts a local session (offline-session.ts). It checks it itself when:
//   the browser says there is no network       the call could only fail
//   the home page says the server is away      no answer to `me`, or a logout not heard yet: a login sent
//                                              then could land before the logout and be ended by it (UI-4)
//   the call itself gets no answer, or a 5xx   the network or the server went as the PIN was sent
// Its no reads as the server's would, in the same words: a wrong PIN, a lock, a suspension; and one of its
// own, for someone this laptop has no check of: log in once with the network.
//
// Sent through the store (useMutation), so a device.blocked answer locks the app at once (noticeBlock,
// device-check.tsx): a call sent around the store would leave a blocked laptop open.
//
// It calls the server, so it lives outside the counter lock (rule 5, ADR-0019): the home page shows it.
//
// "use client": it keeps state and asks the server, both in the browser only.
"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useTranslations } from "use-intl";

import { api } from "@/api/client";
import { forgetTheLastPerson, mayPassLater } from "@/api/query-client";
import { answerOf } from "@/api/refusal";
import { ApiErrorAlert } from "@/components/api-error-alert";
import { Button } from "@/components/design/button";
import type { ShopDatabase } from "@/offline/db";
import { useOnline } from "@/offline/network";
import { checkPinOffline, rememberPin } from "@/offline/pin";
import { useShopDatabase } from "@/offline/this-shop";

import { PinPad } from "./pin-pad";
import { StaffPicker, type StaffRow } from "./staff-picker";

/** Who, and the PIN typed. */
interface Sent {
  staff: string;
  pin: string;
}

export function PinLogin({
  notice,
  onPick,
  serverAway = false,
  onOffline,
}: {
  /** Why the last session ended, when it didn't end by itself: `me` refused it, as when the person was
   * suspended while logged in. Shown above the tiles until someone is picked. */
  notice?: unknown;
  /** Called as a tile is tapped: the home page then drops the notice for good, so Rudi doesn't bring the
   * last person's reason back for the next one (UI-4's review). */
  onPick?: () => void;
  /** The home page knows the server can't be asked now: `me` got no answer, or a logout waits unheard.
   * The PIN is then checked on this laptop, never sent. */
  serverAway?: boolean;
  /** Called with the person after the laptop's own yes: the home page starts their local session. */
  onOffline?: (person: StaffRow) => Promise<void> | void;
}) {
  const t = useTranslations("login.pin");
  const store = useQueryClient();
  const db = useShopDatabase();
  const online = useOnline();
  // Who tapped their tile: nobody yet, so the tiles show.
  const [person, setPerson] = useState<StaffRow | null>(null);

  // The server's answer. Waits in the store's one queue of changes, behind any change made before it.
  const login = useMutation({
    mutationFn: async (sent: Sent): Promise<StaffRow | null> => {
      try {
        await answerOf(api.POST("/api/auth/pin-login/", { body: sent }));
      } catch (error) {
        // No answer at all, or the server broken: the network went as the PIN was sent. The laptop's own
        // check, as if there had been no network from the start. A refusal the server meant stands.
        if (mayPassLater(error)) return checkHere(db, sent);
        throw error;
      }
      // The server's yes: the laptop's check of this PIN, for a login with no network later. Not waited for,
      // so the person doesn't wait for the blender either; a failure to save it (the browser's storage full)
      // costs only that later login, never this one. The PIN lives on in this one call until it is saved.
      if (db !== null)
        void rememberPin(db, sent.staff, sent.pin).catch(() => undefined);
      return null;
    },
    // Waited for: the keys stay off until the store has forgotten the last person, so nothing typed
    // meanwhile sends a second PIN. The forgetting empties `me`, and the home page then says to wait
    // (Subiri kidogo…) until it answers for this person. A yes of the laptop's own goes to the home page.
    onSuccess: (offlinePerson) =>
      offlinePerson ? onOffline?.(offlinePerson) : forgetTheLastPerson(store),
    // Let go of the moment no screen holds it, not after TanStack's 5 minutes: a wrong PIN may be someone's
    // real one, typed on a coworker's tile (UI-4's review).
    gcTime: 0,
    // Once the server has answered, right or wrong, the PIN is rubbed off what was sent: the try stays on
    // the screen to show its answer, but holds no PIN, in the store or in the browser's tools.
    onSettled: (_answer, _error, sent) => {
      sent.pin = "";
    },
  });

  // The laptop's own answer, when the server can't be asked. A line of its own, not the store's queue of
  // changes, and run with no network too: it calls nothing, and a logout waiting in that queue for the
  // network must not hold it back. Let go of, and rubbed, as the server's try is.
  const here = useMutation({
    mutationFn: (sent: Sent) => checkHere(db, sent),
    scope: { id: "pin-checked-here" },
    networkMode: "always",
    onSuccess: (offlinePerson) => onOffline?.(offlinePerson),
    gcTime: 0,
    onSettled: (_answer, _error, sent) => {
      sent.pin = "";
    },
  });

  // One try at a time, whichever way it went: its waiting, and its no.
  const pending = login.isPending || here.isPending;
  const refused = login.error ?? here.error;

  function send(pin: string) {
    if (person === null) return;
    const sent = { staff: person.id, pin };
    // Only one of the two holds a try, so the no shown is this try's.
    if (!online || serverAway) {
      login.reset();
      here.mutate(sent);
    } else {
      here.reset();
      login.mutate(sent);
    }
  }

  // The pad's step: focus on the person's name as it comes, and again once an answer is in, as a key
  // switched off while the PIN was away lets go of the focus. A screen reader says whose PIN it asks for;
  // the tiles' step focuses its own question (staff-picker.tsx).
  const padHeading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    if (!pending) padHeading.current?.focus();
  }, [person, pending]);

  // Back to the tiles, with the last refusal forgotten: the next person starts clean.
  function back() {
    login.reset();
    here.reset();
    setPerson(null);
  }

  // Step 1: the tiles, with the reason the last session ended above them, if it had one.
  if (person === null)
    return (
      <div className="grid gap-6">
        <ApiErrorAlert error={notice} />
        <StaffPicker
          onPick={(picked) => {
            onPick?.();
            setPerson(picked);
          }}
        />
      </div>
    );

  // Step 2: the pad, under the name of the person picked.
  return (
    <div className="grid justify-items-center gap-6">
      <h1
        ref={padHeading}
        tabIndex={-1}
        className="text-3xl font-semibold outline-none"
      >
        {person.full_name}
      </h1>
      <p className="text-lg">{t("typePin")}</p>
      {/* The no, the server's or the laptop's: a wrong PIN, a lock with its minutes, a suspension. */}
      <ApiErrorAlert error={refused} />
      <PinPad onPin={send} disabled={pending} />
      {/* Off while the PIN is on its way too: the answer could still log the person in, behind the
          tiles the next person would see. */}
      <Button kind="second" onClick={back} disabled={pending}>
        {t("back")}
      </Button>
    </div>
  );
}

// The laptop's own check. The home page shows the PIN login only on a registered laptop, whose shop's
// database is open; with none, there is nothing to check against.
function checkHere(db: ShopDatabase | null, sent: Sent): Promise<StaffRow> {
  if (db === null) throw new Error("This laptop belongs to no shop.");
  return checkPinOffline(db, sent.staff, sent.pin);
}
