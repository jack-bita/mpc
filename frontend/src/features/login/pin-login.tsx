// pin-login.tsx — logging in by PIN at a shop's shared device, in two steps: "Wewe ni nani?" with a tile
// for each person (staff-picker.tsx), then the pad under the person's name (pin-pad.tsx) (UI-4, 03 §5.9).
//
// The 4th digit sends who and the PIN to POST /api/auth/pin-login/, with the device's key in its cookie.
// A yes starts a session for that person on this device and answers 204 with nothing: the store then
// forgets the last person (forgetTheLastPerson), which asks `me` again, and the home page shows who is
// here (UI-4). A no shows the server's reason above the pad, which is ready for the next try: a wrong PIN,
// a lock with its minutes, a suspension.
//
// Sent through the store (useMutation), so a device.blocked answer locks the app at once (noticeBlock,
// device-check.tsx): a call sent around the store would leave a blocked laptop open.
//
// It calls the server, so it lives outside the counter lock (rule 5, ADR-0019): the home page shows it.
//
// "use client": it keeps state and asks the server, both in the browser only.
"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslations } from "use-intl";

import { api } from "@/api/client";
import { forgetTheLastPerson } from "@/api/query-client";
import { answerOf } from "@/api/refusal";
import { ApiErrorAlert } from "@/components/api-error-alert";
import { Button } from "@/components/design/button";

import { PinPad } from "./pin-pad";
import { type PinScreenStaff, StaffPicker } from "./staff-picker";

export function PinLogin({
  notice,
  onPick,
}: {
  /** Why the last session ended, when it didn't end by itself: `me` refused it, as when the person was
   * suspended while logged in. Shown above the tiles until someone is picked. */
  notice?: unknown;
  /** Called as a tile is tapped: the home page then drops the notice for good, so Rudi doesn't bring the
   * last person's reason back for the next one (UI-4's review). */
  onPick?: () => void;
}) {
  const t = useTranslations("login.pin");
  const store = useQueryClient();
  // Who tapped their tile: nobody yet, so the tiles show.
  const [person, setPerson] = useState<PinScreenStaff | null>(null);

  const login = useMutation({
    mutationFn: (sent: { staff: string; pin: string }) =>
      answerOf(api.POST("/api/auth/pin-login/", { body: sent })),
    // Waited for: the keys stay off until the store has forgotten the last person and `me` has answered
    // for this one, so nothing typed meanwhile sends a second PIN.
    onSuccess: () => forgetTheLastPerson(store),
  });

  // Back to the tiles, with the last refusal forgotten: the next person starts clean.
  function back() {
    login.reset();
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
      <h1 className="text-3xl font-semibold">{person.full_name}</h1>
      <p className="text-lg">{t("typePin")}</p>
      {/* The server's no: a wrong PIN, a lock with its minutes, a suspension. */}
      <ApiErrorAlert error={login.error} />
      <PinPad
        onPin={(pin) => login.mutate({ staff: person.id, pin })}
        disabled={login.isPending}
      />
      {/* Off while the PIN is on its way too: the answer could still log the person in, behind the
          tiles the next person would see. */}
      <Button kind="second" onClick={back} disabled={login.isPending}>
        {t("back")}
      </Button>
    </div>
  );
}
